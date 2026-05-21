"""
ground_truth.py — Calcula los valores verdaderos para Q1, Q2 y Q3
ejecutando PandaPower puro sobre las redes CR, sin pasar por GridMind.

Es la línea base contra la que el Día 7 compara las respuestas del agente.

Versión: Día 8 (post-fix)
Cambio respecto a Día 7 original: usa el `red_cr_loader.py` del Día 6
(con sistema de backup automático) en vez del antiguo `gt_loader.py`.
Esto evita la contaminación del archivo Base_CR_Max_2023-Marzo.xlsx que
ocurría al cargar varios escenarios en la misma sesión.

Convenciones (coherentes con Día 4 y con tools.py de Día 6):
  - Q1 (resumen): Vmin, Vmax, max line loading (%), n_buses, n_buses_with_result
  - Q2 (subtensiones): conteo y top-5 con vm_pu < 0.95
  - Q3 (sobrecargas): conteo y top-5 con loading_percent > 100, sólo líneas
"""

import math
from red_cr_loader import cargar_red_cr as _cargar_red_cr_d6


# El loader del Día 6 espera "Min"/"Med"/"Max" (sin prefijo "CR_");
# este wrapper acepta ambas formas para no romper código que ya pasa
# "CR_Min" / "CR_Med" / "CR_Max".
def cargar_red_cr(escenario):
    """Adapter: 'CR_Min' -> 'Min' antes de pasar al loader del Día 6."""
    if escenario.startswith("CR_"):
        escenario = escenario[3:]
    return _cargar_red_cr_d6(escenario)


def _safe_min(serie):
    s = serie.dropna()
    return float(s.min()) if len(s) else math.nan


def _safe_max(serie):
    s = serie.dropna()
    return float(s.max()) if len(s) else math.nan


def gt_q1_resumen(escenario):
    """Q1: resumen general de la red post-flujo."""
    net = cargar_red_cr(escenario)
    res_bus = net.res_bus
    res_line = net.res_line

    vm = res_bus["vm_pu"].dropna()
    line_loading = res_line["loading_percent"].dropna()

    return {
        "escenario": escenario,
        "converged": True,  # red_cr.py corrió pp.runpp con éxito
        "n_buses": int(len(net.bus)),
        "n_buses_with_result": int(len(vm)),
        "v_min_pu": float(vm.min()),
        "v_max_pu": float(vm.max()),
        "max_line_loading_percent": float(line_loading.max()) if len(line_loading) else math.nan,
    }


def gt_q2_subtensiones(escenario, v_min=0.95):
    """Q2: barras con vm_pu < v_min, conteo y top-5 más bajas."""
    net = cargar_red_cr(escenario)
    res_bus = net.res_bus.copy()
    res_bus = res_bus.dropna(subset=["vm_pu"])

    sub = res_bus[res_bus["vm_pu"] < v_min].sort_values("vm_pu", ascending=True)
    top5 = sub.head(5)

    return {
        "escenario": escenario,
        "v_min_threshold": v_min,
        "n_subtension": int(len(sub)),
        "top5": [
            {"bus_index": int(idx), "vm_pu": float(row["vm_pu"])}
            for idx, row in top5.iterrows()
        ],
    }


def gt_q3_sobrecargas(escenario, threshold=100.0):
    """Q3: líneas con loading_percent > threshold, conteo y top-5."""
    net = cargar_red_cr(escenario)
    res_line = net.res_line.copy().dropna(subset=["loading_percent"])

    over = (
        res_line[res_line["loading_percent"] > threshold]
        .sort_values("loading_percent", ascending=False)
    )
    top5 = over.head(5)

    items = []
    for idx, row in top5.iterrows():
        from_bus = int(net.line.loc[idx, "from_bus"])
        to_bus = int(net.line.loc[idx, "to_bus"])
        items.append({
            "line_index": int(idx),
            "from_bus": from_bus,
            "to_bus": to_bus,
            "loading_percent": float(row["loading_percent"]),
        })

    return {
        "escenario": escenario,
        "loading_threshold": threshold,
        "n_overloads": int(len(over)),
        "top5": items,
    }


def ground_truth_completo(escenario):
    """Devuelve los 3 ground truths para un escenario."""
    return {
        "Q1_resumen": gt_q1_resumen(escenario),
        "Q2_subtensiones": gt_q2_subtensiones(escenario),
        "Q3_sobrecargas": gt_q3_sobrecargas(escenario),
    }


if __name__ == "__main__":
    import json
    for esc in ["CR_Min", "CR_Med", "CR_Max"]:
        print("=" * 70)
        print(esc)
        print("=" * 70)
        gt = ground_truth_completo(esc)
        print(json.dumps(gt, indent=2, ensure_ascii=False))
        print()
