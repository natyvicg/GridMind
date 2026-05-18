"""
correr_bateria_v2.py — Batería de pruebas con validación de umbrales.
Incluye check post-ejecución del uso correcto de umbrales en CR_Min·Q2.

Igual que correr_bateria.py (resume + timeout + persistencia
incremental + precarga visible) pero escribe a logs/log_bateria_v2.json
para no pisar el log original (que sirve como evidencia del antes).

Al final imprime un comparativo: si CR_Min·Q2 ahora usa v_max=1.05 (en vez
de 1.25415), la mitigación funcionó.

Uso:
    python correr_bateria_v2.py
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from agent import run_react_loop
from red_cr_loader import cargar_red_cr


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

PRECIO_INPUT_USD_POR_MTOK = 3.00
PRECIO_OUTPUT_USD_POR_MTOK = 15.00

TIMEOUT_API_S = 90.0
MAX_RETRIES_API = 2

LOG_PATH = Path("logs/log_bateria_v2.json")  # ← clave: archivo nuevo

# ---------------------------------------------------------------------------
# Batería de consultas
# ---------------------------------------------------------------------------

ESCENARIOS = ["CR_Min", "CR_Med", "CR_Max"]

CONSULTAS = [
    {
        "consulta_id": "Q1_resumen",
        "query_template": (
            "Carga la red {esc} y dame un resumen del estado: "
            "¿convergió el flujo? ¿cuál es el rango de tensiones (Vmin, Vmax)? "
            "¿cuál es la carga máxima de líneas y de transformadores?"
        ),
    },
    {
        "consulta_id": "Q2_subtensiones",
        "query_template": (
            "Para la red {esc}, ¿cuántas barras presentan violaciones de tensión? "
            "Lista las 5 más severas y comenta el patrón si lo hay."
        ),
    },
    {
        "consulta_id": "Q3_sobrecargas",
        "query_template": (
            "En la red {esc}, ¿hay líneas sobrecargadas (cargabilidad mayor a 100%)? "
            "Si las hay, lista hasta 5; si no, confírmalo explícitamente."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _calcular_costo(input_tokens, output_tokens):
    return (
        input_tokens / 1_000_000 * PRECIO_INPUT_USD_POR_MTOK
        + output_tokens / 1_000_000 * PRECIO_OUTPUT_USD_POR_MTOK
    )


def _cargar_log_previo():
    """Si ya existen consultas exitosas en v2, las recuperamos."""
    if not LOG_PATH.exists():
        return {"resultados": [], "totales": {"input_tokens": 0, "output_tokens": 0, "costo_usd": 0.0}}
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Filtrar solo exitosas (no error)
        ok = [r for r in data["resultados"] if not r.get("error")]
        data["resultados"] = ok
        return data
    except Exception:
        return {"resultados": [], "totales": {"input_tokens": 0, "output_tokens": 0, "costo_usd": 0.0}}


def _ya_corrida(log, esc, qid):
    return any(
        r["escenario"] == esc and r["consulta_id"] == qid
        for r in log["resultados"]
    )


def _persistir(log):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

def main():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: no se encontró ANTHROPIC_API_KEY en el entorno.")
        sys.exit(1)

    print(f"[{_ts()}] === BATERÍA CON VALIDACIÓN DE UMBRALES ===")
    print(f"[{_ts()}] Log destino: {LOG_PATH}")
    print(f"[{_ts()}] (Si ya existe, se reanuda y se SALTAN consultas exitosas previas)")
    print()

    # 1. Precarga de redes — gratis, antes de tocar API
    print(f"[{_ts()}] Precargando redes CR (sin agente, sin costo USD)...")
    for esc in ESCENARIOS:
        t0 = time.time()
        net = cargar_red_cr(esc.replace("CR_", ""))
        dt = time.time() - t0
        v = net.res_bus["vm_pu"].dropna()
        print(f"  [{_ts()}] {esc} listo en {dt:.1f}s | Vmin={v.min():.4f} Vmax={v.max():.4f}")
    print(f"[{_ts()}] Precarga completa.")
    print()

    # 2. Cliente Anthropic con timeout y reintentos
    client = Anthropic(api_key=api_key, timeout=TIMEOUT_API_S, max_retries=MAX_RETRIES_API)

    # 3. Cargar log previo para resume
    log = _cargar_log_previo()
    n_ya = len(log["resultados"])
    if n_ya > 0:
        print(f"[{_ts()}] Resume: {n_ya} consulta(s) exitosa(s) ya en log v2, se saltarán.")
        print()

    # 4. Loop por (escenario, consulta)
    for esc in ESCENARIOS:
        print(f"--- Escenario: {esc} ---")
        for c in CONSULTAS:
            qid = c["consulta_id"]
            if _ya_corrida(log, esc, qid):
                print(f"[{_ts()}] [{qid}] (ya en log, salto)")
                continue

            query = c["query_template"].format(esc=esc)
            print(f"[{_ts()}] [{qid}] {query[:60]}...")

            t0 = time.time()
            try:
                res = run_react_loop(query, client=client, verbose=True)
                dt = time.time() - t0
            except Exception as e:
                dt = time.time() - t0
                print(f"  [{_ts()}] ERROR tras {dt:.1f}s: {type(e).__name__}: {e}")
                # Persistimos el error para no perder evidencia
                log["resultados"].append({
                    "escenario": esc,
                    "consulta_id": qid,
                    "query": query,
                    "error": f"{type(e).__name__}: {e}",
                    "elapsed_s": dt,
                })
                _persistir(log)
                continue

            costo = _calcular_costo(res["usage"]["input_tokens"], res["usage"]["output_tokens"])
            print(
                f"  [{_ts()}] Listo: iters={res['iterations']} "
                f"tools={len(res['tool_calls'])} costo=${costo:.4f} t={dt:.1f}s"
            )

            log["resultados"].append({
                "escenario": esc,
                "consulta_id": qid,
                "query": query,
                "iterations": res["iterations"],
                "stop_reason": res["stop_reason"],
                "tool_calls": [
                    {"name": tc["name"], "input": tc["input"], "result": str(tc["result"])}
                    for tc in res["tool_calls"]
                ],
                "final_text": res["final_text"],
                "usage": res["usage"],
                "costo_usd": costo,
                "elapsed_s": dt,
                "error": None,
            })

            # Recalcular totales y persistir tras cada consulta
            log["totales"] = {
                "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0) for r in log["resultados"] if not r.get("error")),
                "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in log["resultados"] if not r.get("error")),
                "costo_usd": sum(r.get("costo_usd", 0) for r in log["resultados"] if not r.get("error")),
            }
            _persistir(log)
        print()

    # 5. Reporte de cierre
    print(f"[{_ts()}] === BATERÍA COMPLETADA ===")
    print(f"  Total consultas exitosas: {sum(1 for r in log['resultados'] if not r.get('error'))}")
    print(f"  Total tokens input:       {log['totales']['input_tokens']:,}")
    print(f"  Total tokens output:      {log['totales']['output_tokens']:,}")
    print(f"  Costo total:              ${log['totales']['costo_usd']:.4f} USD")
    print(f"  Log:                      {LOG_PATH}")
    print()

    # 6. CHECK de umbrales en CR_Min·Q2
    print(f"[{_ts()}] === CHECK DE UMBRALES ===")
    bug_target = next(
        (r for r in log["resultados"]
         if r["escenario"] == "CR_Min" and r["consulta_id"] == "Q2_subtensiones"
         and not r.get("error")),
        None
    )
    if bug_target is None:
        print("  CR_Min·Q2 no se ejecutó esta vuelta — sin check.")
    else:
        # Buscar la llamada a get_voltage_violations
        gvv = next(
            (tc for tc in bug_target["tool_calls"] if tc["name"] == "get_voltage_violations"),
            None
        )
        if gvv is None:
            print("  CR_Min·Q2 no llamó a get_voltage_violations — patrón distinto al esperado.")
        else:
            args = gvv["input"]
            v_max = args.get("v_max")
            v_min = args.get("v_min")
            print(f"  CR_Min·Q2 → get_voltage_violations(v_min={v_min}, v_max={v_max})")
            if v_max is None or abs(v_max - 1.05) < 1e-6:
                print(f"  ✅ MITIGACIÓN OK: v_max es {v_max} (estándar 1.05).")
            elif v_max > 1.15:
                print(f"  ❌ REGRESIÓN: v_max={v_max} sigue siendo inusualmente alto.")
            else:
                print(f"  ⚠️  v_max={v_max}: distinto al estándar pero dentro del rango aceptable.")

    print()
    print(f"[{_ts()}] Próximo paso: correr validar_agente.py apuntando a {LOG_PATH.name}")
    print(f"           Resultado esperado: 108/108 chequeos coinciden (100 %).")


if __name__ == "__main__":
    main()
