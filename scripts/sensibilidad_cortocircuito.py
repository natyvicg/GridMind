"""
sensibilidad_cortocircuito.py — Análisis de sensibilidad al supuesto de
potencia de cortocircuito de las interconexiones.

Motivación
----------
El modelo de la red CR representa las conexiones con Nicaragua y Panamá
como cinco fuentes ideales (ext_grid). Una fuente ideal tiene impedancia
nula, lo que es inadmisible en un cálculo de cortocircuito, y el modelo
de origen no especifica su potencia de cortocircuito equivalente.

Ese dato, por tanto, es un supuesto. Este script cuantifica cuánto
importa: barre la potencia de cortocircuito asumida y mide el efecto
sobre las corrientes de falla, separando las barras de interconexión del
resto de la red.

Con el modelo verificado (revisión 73a3451 en adelante), el supuesto
domina la corriente en las cinco barras de interconexión y mueve alrededor
de 10 % la mediana y la máxima del resto de la red en todo el barrido.

Salida
------
  - Tabla en consola, lista para el TFG.
  - sensibilidad_cortocircuito.xlsx con la misma tabla.

Uso:
    python -m scripts.sensibilidad_cortocircuito
"""

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

# Barras donde red_cr.py conecta las interconexiones.
BARRAS_INTERCONEXION = [50000, 50050, 56050, 56052, 58350]

# Potencias de cortocircuito a evaluar (MVA).
BARRIDO_MVA = [500, 1000, 2000, 5000, 10000, 20000]

ESCENARIO = "Max"


def corrida(escenario, s_sc_mva):
    """Devuelve la serie de corrientes Ikss por barra para un supuesto."""
    net = cargar_red_cr(escenario, forzar_recarga=True)
    net, _ = preparar_red_cr(net, escenario, s_sc_interconexion_mva=s_sc_mva)
    pp_sc.calc_sc(net, fault="3ph", case="max")
    return net.res_bus_sc["ikss_ka"].dropna()


def main():
    print("=" * 78)
    print("SENSIBILIDAD AL SUPUESTO DE POTENCIA DE CORTOCIRCUITO")
    print("Red CR_{} — falla trifásica, caso máximo, IEC 60909".format(ESCENARIO))
    print("=" * 78)
    print()
    print("Las 5 barras de interconexión son: {}".format(
        ", ".join(str(b) for b in BARRAS_INTERCONEXION)))
    print("El modelo de origen no especifica su potencia de cortocircuito.")
    print()

    filas = []
    for s_sc in BARRIDO_MVA:
        ik = corrida(ESCENARIO, s_sc)
        presentes = [b for b in BARRAS_INTERCONEXION if b in ik.index]
        interconex = ik.loc[presentes]
        resto = ik.drop(presentes)
        filas.append({
            "S_cc asumida (MVA)": s_sc,
            "Icc media en interconexión (kA)": round(float(interconex.mean()), 2),
            "Icc mediana del resto (kA)": round(float(resto.median()), 3),
            "Icc máxima del resto (kA)": round(float(resto.max()), 2),
            "Barras con resultado": int(len(ik)),
        })
        print("  S_cc = {:>6} MVA  →  interconexión {:>6.2f} kA  |  "
              "resto: mediana {:.3f} kA, máxima {:.2f} kA".format(
                  s_sc,
                  filas[-1]["Icc media en interconexión (kA)"],
                  filas[-1]["Icc mediana del resto (kA)"],
                  filas[-1]["Icc máxima del resto (kA)"]))

    df = pd.DataFrame(filas)

    print()
    print("-" * 78)
    med_min = df["Icc mediana del resto (kA)"].iloc[0]
    med_max = df["Icc mediana del resto (kA)"].iloc[-1]
    var_resto = 100.0 * (med_max - med_min) / med_min
    inter_min = df["Icc media en interconexión (kA)"].iloc[0]
    inter_max = df["Icc media en interconexión (kA)"].iloc[-1]
    var_inter = 100.0 * (inter_max - inter_min) / inter_min

    print("Variando el supuesto de {} a {} MVA (factor {:.0f}):".format(
        BARRIDO_MVA[0], BARRIDO_MVA[-1], BARRIDO_MVA[-1] / BARRIDO_MVA[0]))
    print("  Barras de interconexión: la corriente varía {:+.1f} %".format(var_inter))
    print("  Resto de la red:         la mediana varía {:+.1f} %".format(var_resto))
    print()
    print("Lectura: el supuesto domina la corriente en las barras de")
    print("interconexión y mueve la mediana del resto de la red en el")
    print("porcentaje indicado arriba. Debe declararse con cada resultado y")
    print("fijarse igual en GridMind y en ETAP antes de comparar.")
    print("-" * 78)

    salida = "sensibilidad_cortocircuito.xlsx"
    df.to_excel(salida, index=False, sheet_name="Sensibilidad")
    print()
    print("Tabla exportada a {}".format(salida))

    print()
    print("Tabla en Markdown (para pegar en el TFG):")
    print()
    print(df.to_markdown(index=False))

    return df


if __name__ == "__main__":
    main()
