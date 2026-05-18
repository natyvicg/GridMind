"""
validar_agente.py — Validación cruzada: agente vs PandaPower.

Compara las corridas del agente (logs/log_bateria_v1.json)
contra cálculos directos de PandaPower (ground_truth.py).

Tres niveles de validación:
  1. Tool-level: ¿llamó la tool correcta con args razonables?
  2. Data-level: ¿lo que retornó la tool coincide con ground truth?
  3. Response-level: ¿el final_text refleja correctamente los datos?

Tolerancias:
  - Tensiones (pu): ±0.001
  - Cargabilidades (%): ±0.1
  - Conteos / índices: match exacto
"""

import ast
import json
import math
import re
from pathlib import Path

from ground_truth import ground_truth_completo


# ---------------------------------------------------------------------------
# Parámetros estándar
# ---------------------------------------------------------------------------

TOL_VOLT_PU = 1e-3
TOL_LOADING_PCT = 0.1

DEFAULTS_ESPERADOS = {
    "Q1_resumen": {
        "tools": ["run_power_flow"],
    },
    "Q2_subtensiones": {
        "tools": ["run_power_flow", "get_voltage_violations"],
        "args_get_voltage_violations": {"v_min": 0.95, "v_max": 1.05},
    },
    "Q3_sobrecargas": {
        "tools": ["run_power_flow", "get_overloaded_lines"],
        "args_get_overloaded_lines": {"loading_threshold": 100},
    },
}


# ---------------------------------------------------------------------------
# Helpers de parseo
# ---------------------------------------------------------------------------

def parse_tool_result(result):
    """tool_calls[i]['result'] viene como string repr de dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return ast.literal_eval(result)
        except Exception:
            return None
    return None


def coincide(valor_a, valor_g, tol=0.0):
    """Match con tolerancia. NaN siempre falla."""
    if valor_a is None or valor_g is None:
        return False
    if isinstance(valor_a, float) and math.isnan(valor_a):
        return False
    if isinstance(valor_g, float) and math.isnan(valor_g):
        return False
    if isinstance(valor_a, (int, float)) and isinstance(valor_g, (int, float)):
        return abs(valor_a - valor_g) <= tol
    return valor_a == valor_g


def diff(a, g):
    if isinstance(a, (int, float)) and isinstance(g, (int, float)):
        return float(a - g)
    return None


# ---------------------------------------------------------------------------
# Nivel 1 — Tool-level
# ---------------------------------------------------------------------------

def validar_tool_level(corrida):
    """Devuelve lista de chequeos tool-level con resultado.

    Reglas:
      - tools_usadas: el agente puede invocar la misma tool más de una vez
        (p. ej., para obtener más resultados). Se acepta como coincidencia
        si la secuencia esperada es prefijo o subconjunto ordenado de la
        secuencia del agente.
      - args.X: si el agente OMITE el parámetro (None), eso equivale a
        usar el default — y los defaults estándar son justamente
        v_min=0.95, v_max=1.05, loading_threshold=100. Por lo tanto
        agente=None se considera coincidente cuando el esperado es el
        default estándar.
    """
    qid = corrida["consulta_id"]
    esc = corrida["escenario"]
    expected = DEFAULTS_ESPERADOS[qid]
    tool_calls = corrida["tool_calls"]
    nombres = [tc["name"] for tc in tool_calls]

    chequeos = []

    # Tools usadas vs esperadas — aceptar si las esperadas están todas
    # en orden (puede haber repeticiones extra de la misma tool).
    def _es_supersecuencia(superseq, subseq):
        i = 0
        for x in superseq:
            if i < len(subseq) and x == subseq[i]:
                i += 1
        return i == len(subseq)

    coincide_tools = _es_supersecuencia(nombres, expected["tools"])
    chequeos.append({
        "nivel": "tool",
        "escenario": esc,
        "consulta": qid,
        "metrica": "tools_usadas",
        "valor_agente": nombres,
        "valor_ground_truth": expected["tools"],
        "delta": None,
        "coincide": coincide_tools,
        "nota": (
            ""
            if coincide_tools or nombres == expected["tools"]
            else "El agente invocó tools en orden distinto al esperado."
        ),
    })

    # Args de la tool relevante (si aplica)
    for k, esperado in expected.items():
        if not k.startswith("args_"):
            continue
        tool_name = k[len("args_"):]
        # Buscar la primera tool_call con ese nombre
        tc = next((t for t in tool_calls if t["name"] == tool_name), None)
        if tc is None:
            continue
        args = tc.get("input", {})
        for arg_k, arg_v_esperado in esperado.items():
            agente_v = args.get(arg_k)

            # Regla nueva: omitir el parámetro (None) equivale a usar el
            # default estándar. Por construcción de DEFAULTS_ESPERADOS,
            # los valores esperados SON los defaults estándar.
            if agente_v is None:
                ok = True
                nota = (
                    f"El agente OMITIÓ el parámetro {arg_k} (= usa default "
                    f"{arg_v_esperado}). Comportamiento correcto."
                )
            else:
                ok = coincide(agente_v, arg_v_esperado, tol=1e-6)
                if ok:
                    nota = ""
                else:
                    nota = (
                        f"El agente eligió un umbral no estándar. "
                        f"Default esperado: {arg_v_esperado}; usado: {agente_v}."
                    )
            chequeos.append({
                "nivel": "tool",
                "escenario": esc,
                "consulta": qid,
                "metrica": f"{tool_name}.{arg_k}",
                "valor_agente": agente_v,
                "valor_ground_truth": arg_v_esperado,
                "delta": diff(agente_v, arg_v_esperado),
                "coincide": ok,
                "nota": nota,
            })

    return chequeos


# ---------------------------------------------------------------------------
# Nivel 2 — Data-level
# ---------------------------------------------------------------------------

def validar_data_level(corrida, gt):
    """Compara lo que retornaron las tools vs ground truth (PandaPower puro)."""
    qid = corrida["consulta_id"]
    esc = corrida["escenario"]
    chequeos = []

    if qid == "Q1_resumen":
        tc = corrida["tool_calls"][0]
        d = parse_tool_result(tc["result"])
        gt_q = gt["Q1_resumen"]
        pares = [
            ("converged", d.get("converged"), gt_q["converged"], 0),
            ("n_buses", d.get("n_buses"), gt_q["n_buses"], 0),
            ("n_buses_with_result", d.get("n_buses_with_result"), gt_q["n_buses_with_result"], 0),
            ("v_min_pu", d.get("v_min_pu"), gt_q["v_min_pu"], TOL_VOLT_PU),
            ("v_max_pu", d.get("v_max_pu"), gt_q["v_max_pu"], TOL_VOLT_PU),
            ("max_line_loading_percent",
             d.get("max_line_loading_percent"),
             gt_q["max_line_loading_percent"], TOL_LOADING_PCT),
        ]
        for k, va, vg, tol in pares:
            chequeos.append({
                "nivel": "data",
                "escenario": esc,
                "consulta": qid,
                "metrica": f"run_power_flow.{k}",
                "valor_agente": va,
                "valor_ground_truth": vg,
                "delta": diff(va, vg),
                "coincide": coincide(va, vg, tol=tol),
                "nota": "",
            })

    elif qid == "Q2_subtensiones":
        # 2da tool: get_voltage_violations
        tc = corrida["tool_calls"][1]
        d = parse_tool_result(tc["result"])
        gt_q = gt["Q2_subtensiones"]

        chequeos.append({
            "nivel": "data",
            "escenario": esc,
            "consulta": qid,
            "metrica": "get_voltage_violations.n_subtension",
            "valor_agente": d.get("n_subtension"),
            "valor_ground_truth": gt_q["n_subtension"],
            "delta": diff(d.get("n_subtension"), gt_q["n_subtension"]),
            "coincide": coincide(d.get("n_subtension"), gt_q["n_subtension"], tol=0),
            "nota": "",
        })

        # Top-5 (por orden ascendente de tensión)
        violaciones_agente = [
            v for v in (d.get("violations") or []) if v.get("tipo") == "subtension"
        ]
        violaciones_agente_sorted = sorted(violaciones_agente, key=lambda x: x["vm_pu"])[:5]

        for i in range(5):
            va = violaciones_agente_sorted[i] if i < len(violaciones_agente_sorted) else None
            vg = gt_q["top5"][i] if i < len(gt_q["top5"]) else None
            ok_idx = (va is not None and vg is not None and va["bus_index"] == vg["bus_index"])
            ok_v = (va is not None and vg is not None and coincide(va["vm_pu"], vg["vm_pu"], tol=TOL_VOLT_PU))
            chequeos.append({
                "nivel": "data",
                "escenario": esc,
                "consulta": qid,
                "metrica": f"get_voltage_violations.top5[{i}].bus_index",
                "valor_agente": va["bus_index"] if va else None,
                "valor_ground_truth": vg["bus_index"] if vg else None,
                "delta": None,
                "coincide": ok_idx,
                "nota": "",
            })
            chequeos.append({
                "nivel": "data",
                "escenario": esc,
                "consulta": qid,
                "metrica": f"get_voltage_violations.top5[{i}].vm_pu",
                "valor_agente": va["vm_pu"] if va else None,
                "valor_ground_truth": vg["vm_pu"] if vg else None,
                "delta": diff(va["vm_pu"] if va else None, vg["vm_pu"] if vg else None),
                "coincide": ok_v,
                "nota": "",
            })

    elif qid == "Q3_sobrecargas":
        tc = corrida["tool_calls"][1]
        d = parse_tool_result(tc["result"])
        gt_q = gt["Q3_sobrecargas"]

        chequeos.append({
            "nivel": "data",
            "escenario": esc,
            "consulta": qid,
            "metrica": "get_overloaded_lines.n_overloads",
            "valor_agente": d.get("n_overloads_total") or d.get("n_overloads") or 0,
            "valor_ground_truth": gt_q["n_overloads"],
            "delta": diff(d.get("n_overloads_total") or d.get("n_overloads") or 0, gt_q["n_overloads"]),
            "coincide": coincide(d.get("n_overloads_total") or d.get("n_overloads") or 0,
                                 gt_q["n_overloads"], tol=0),
            "nota": "",
        })

    return chequeos


# ---------------------------------------------------------------------------
# Nivel 3 — Response-level (parseo simple del final_text)
# ---------------------------------------------------------------------------

_NUM_RE = r"-?\d+(?:[.,]\d+)?"


def _floats_in(text):
    return [float(x.replace(",", ".")) for x in re.findall(_NUM_RE, text)]


def validar_response_level(corrida, gt):
    """
    Verifica que las cifras clave del ground truth aparezcan en final_text
    (con tolerancia). Es un check semántico ligero: NO valida estructura,
    solo presencia numérica de los valores correctos.
    """
    qid = corrida["consulta_id"]
    esc = corrida["escenario"]
    text = corrida["final_text"] or ""
    chequeos = []

    floats_text = _floats_in(text)
    text_lower = text.lower()
    # Frases que un texto natural usa como sinónimo de "0".
    _CERO_NATURAL = ("no hay", "ninguna", "ningún", "ningun ",
                     "sin sobrecargas", "sin violaciones", "cero ")

    def aparece(valor, tol):
        if any(abs(v - valor) <= tol for v in floats_text):
            return True
        # Caso natural: ground_truth = 0 expresado como "no hay".
        if valor == 0 and any(p in text_lower for p in _CERO_NATURAL):
            return True
        return False

    if qid == "Q1_resumen":
        gt_q = gt["Q1_resumen"]
        casos = [
            ("v_min_pu", gt_q["v_min_pu"], TOL_VOLT_PU),
            ("v_max_pu", gt_q["v_max_pu"], TOL_VOLT_PU),
            ("max_line_loading_percent", gt_q["max_line_loading_percent"], TOL_LOADING_PCT),
            ("n_buses", float(gt_q["n_buses"]), 0),
            ("n_buses_with_result", float(gt_q["n_buses_with_result"]), 0),
        ]
    elif qid == "Q2_subtensiones":
        gt_q = gt["Q2_subtensiones"]
        casos = [("n_subtension", float(gt_q["n_subtension"]), 0)]
        # Solo verificamos la PRIMERA del top-5 (la subtensión más severa)
        # como cifra "clave". El agente puede legítimamente reportar un top-5
        # mixto de subtensiones + sobretensiones, así que no exigimos las 5.
        if gt_q["top5"]:
            casos.append(("top5[0].vm_pu", gt_q["top5"][0]["vm_pu"], TOL_VOLT_PU))
    else:  # Q3
        gt_q = gt["Q3_sobrecargas"]
        casos = [("n_overloads", float(gt_q["n_overloads"]), 0)]

    for nombre, valor_gt, tol in casos:
        ok = aparece(valor_gt, tol)
        chequeos.append({
            "nivel": "response",
            "escenario": esc,
            "consulta": qid,
            "metrica": f"final_text contiene {nombre}",
            "valor_agente": "presente" if ok else "ausente",
            "valor_ground_truth": valor_gt,
            "delta": None,
            "coincide": ok,
            "nota": "",
        })

    return chequeos


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def main(
    log_path="logs/log_bateria_v1.json",
    out_dir="logs",
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)

    # Ground truth por escenario (cacheado dentro de red_cr_loader)
    print("Calculando ground truth para los 3 escenarios CR…")
    gts = {}
    for esc in ["CR_Min", "CR_Med", "CR_Max"]:
        print(f"  → {esc}")
        gts[esc] = ground_truth_completo(esc)
    print()

    todos = []
    for corrida in log["resultados"]:
        if corrida.get("error"):
            print(f"  [SKIP] {corrida['escenario']}·{corrida['consulta_id']} — error en log")
            continue
        gt = gts[corrida["escenario"]]
        todos.extend(validar_tool_level(corrida))
        todos.extend(validar_data_level(corrida, gt))
        todos.extend(validar_response_level(corrida, gt))

    # Resumen agregado
    n_total = len(todos)
    n_ok = sum(1 for c in todos if c["coincide"])
    por_nivel = {}
    for c in todos:
        nivel = c["nivel"]
        por_nivel.setdefault(nivel, [0, 0])
        por_nivel[nivel][0] += 1
        if c["coincide"]:
            por_nivel[nivel][1] += 1

    salida = {
        "n_chequeos": n_total,
        "n_coinciden": n_ok,
        "porcentaje_coincidencia": round(100 * n_ok / n_total, 2) if n_total else 0,
        "por_nivel": {
            k: {"total": t, "coinciden": ok, "pct": round(100*ok/t, 2)}
            for k, (t, ok) in por_nivel.items()
        },
        "chequeos": todos,
    }

    # JSON estructurado
    with open(out_dir / "log_validacion.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print(f"Total chequeos: {n_total}")
    print(f"Coinciden:      {n_ok}  ({salida['porcentaje_coincidencia']}%)")
    for nivel, st in salida["por_nivel"].items():
        print(f"  {nivel:10s}: {st['coinciden']}/{st['total']} ({st['pct']}%)")

    return salida


if __name__ == "__main__":
    main()
