"""
sensibilidad_supuestos.py — Sensibilidad de la corriente de cortocircuito a
tres supuestos de la preparación de datos (sección de supuestos del TFG).

Supuestos barridos (escenario CR_Max, falla trifásica, IEC 60909):
  - Relación X/R de las máquinas: 10, 15, 20, 30 y 40 (adoptado: 20), caso máximo.
  - Factor de potencia nominal de las máquinas: 0,80 a 0,95 (adoptado: 0,85), caso máximo.
  - Temperatura final de conductor: 20 a 120 °C (adoptada: 80 °C), caso mínimo,
    con la misma potencia de cortocircuito de red externa que en el caso máximo,
    como hace la herramienta run_short_circuit.

Para cada supuesto reporta la corriente máxima y la mediana de I''k sobre las
barras con resultado, y la variación entre el mayor y el menor valor del
barrido como porcentaje del valor con el supuesto adoptado.

Salida
------
  - Tabla en consola.
  - sensibilidad_supuestos.xlsx con el detalle por valor y el resumen.

Uso:
    python -m scripts.sensibilidad_supuestos
"""

import copy
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

import warnings  # noqa: E402

import pandas as pd  # noqa: E402
import pandapower.shortcircuit as pp_sc  # noqa: E402

from datos_cortocircuito import preparar_red_cr  # noqa: E402
from red_cr_loader import cargar_red_cr  # noqa: E402

warnings.filterwarnings("ignore")

ESCENARIO = "Max"

BARRIDOS = [
    # (nombre, parámetro, valores, valor adoptado, caso)
    ("Relación X/R de las máquinas", "x_r_maquina", [10, 15, 20, 30, 40], 20, "max"),
    ("Factor de potencia nominal", "cos_phi", [0.80, 0.85, 0.90, 0.95], 0.85, "max"),
    ("Temperatura final de conductor (°C)", "endtemp", [20, 50, 80, 100, 120], 80, "min"),
]


def corrida(base, parametro, valor, caso):
    """Corrientes Ikss por barra para un valor del supuesto."""
    net = copy.deepcopy(base)
    kwargs = {}
    if parametro in ("x_r_maquina", "cos_phi"):
        kwargs[parametro] = valor
    net, _ = preparar_red_cr(net, ESCENARIO, **kwargs)
    if caso == "min":
        # Igual que run_short_circuit: el modelo no distingue S"k mínima y máxima.
        net.ext_grid["s_sc_min_mva"] = net.ext_grid["s_sc_max_mva"]
        net.ext_grid["rx_min"] = net.ext_grid["rx_max"]
        net.line["endtemp_degree"] = float(valor)
    pp_sc.calc_sc(net, fault="3ph", case=caso)
    return net.res_bus_sc.ikss_ka.dropna()


def main():
    base = cargar_red_cr(ESCENARIO, forzar_recarga=True)
    detalle, resumen = [], []
    for nombre, parametro, valores, adoptado, caso in BARRIDOS:
        maximos, medianas = {}, {}
        for v in valores:
            ik = corrida(base, parametro, v, caso)
            maximos[v], medianas[v] = ik.max(), ik.median()
            detalle.append({"Supuesto": nombre, "Valor": v, "Caso": caso,
                            "Ik máxima (kA)": round(ik.max(), 4),
                            "Ik mediana (kA)": round(ik.median(), 4),
                            "Barras": len(ik)})
        var_max = 100 * (max(maximos.values()) - min(maximos.values())) / maximos[adoptado]
        var_med = 100 * (max(medianas.values()) - min(medianas.values())) / medianas[adoptado]
        resumen.append({"Supuesto": nombre, "Valor adoptado": adoptado,
                        "Rango barrido": f"{valores[0]} a {valores[-1]}", "Caso": caso,
                        "Variación de la máxima (%)": round(var_max, 3),
                        "Variación de la mediana (%)": round(var_med, 3)})

    df_det, df_res = pd.DataFrame(detalle), pd.DataFrame(resumen)
    print("\nDetalle por valor (CR_Max, falla trifásica):\n")
    print(df_det.to_string(index=False))
    print("\nResumen:\n")
    print(df_res.to_string(index=False))

    salida = RAIZ / "sensibilidad_supuestos.xlsx"
    with pd.ExcelWriter(salida) as xl:
        df_res.to_excel(xl, sheet_name="Resumen", index=False)
        df_det.to_excel(xl, sheet_name="Detalle", index=False)
    print(f"\nGuardado en {salida}")


if __name__ == "__main__":
    main()
