"""
sensibilidad_frontera.py — Sensibilidad a la representación de las
interconexiones con Nicaragua y Panamá.

Motivación
----------
Las cinco barras de frontera de 230 kV (LIB230A, CAS230A, RCL230A,
RCL230B y CAH230) están declaradas en el Excel como barras tipo 1, es
decir barras pasivas: no tienen carga ni generación asociada. El único
nodo de referencia (tipo 3) del modelo exportado es la barra 50120,
DEN-U1, a 13.8 kV.

`red_cr.py` toma otra decisión de modelado: coloca cinco fuentes ideales
(ext_grid) en las barras de frontera y deja la 50120 como generador
común. Esa decisión no está en los datos de entrada y es defendible —
Costa Rica está interconectada y no opera como isla, y la barra swing
interna del archivo es probablemente un artefacto de la exportación
desde PSS/E, donde al recortar el área nacional se perdieron los
equivalentes de frontera. Pero al ser una decisión, cambia los
resultados y debe declararse.

Este script cuantifica cuánto cambia, comparando:

    Modelo A — cinco fuentes ideales en la frontera (lo que usa GridMind)
    Modelo B — nodo de referencia en la barra 50120, sin fuentes de
               frontera (lo que declara el Excel)

Por qué importa para la validación contra ETAP
----------------------------------------------
Si el modelo de ETAP se construye siguiendo el Excel, usará la barra
50120 como swing y sus resultados corresponderán al modelo B. Comparar
el modelo A contra el modelo B produce diferencias que NO son errores de
cálculo: son diferencias de condición de frontera. Igualar la
representación antes de comparar es un paso previo obligatorio del
procedimiento de validación.

Salida
------
  - Tres tablas en consola, listas para el TFG.
  - sensibilidad_frontera.xlsx con una hoja por tabla.
  - Las mismas tablas en Markdown.

Uso:
    python -m scripts.sensibilidad_frontera
"""

import os
import sys
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

import pandas as pd  # noqa: E402
import pandapower as pp  # noqa: E402

from red_cr_loader import cargar_red_cr  # noqa: E402

warnings.filterwarnings("ignore")

ESCENARIOS = ("Min", "Med", "Max")

# Barras donde red_cr.py conecta las interconexiones.
BARRAS_FRONTERA = [50000, 50050, 56050, 56052, 58350]

# Nodo de referencia que declara el Excel (Bus Data, Code 3).
BARRA_SLACK_EXCEL = 50120

# Umbrales operacionales estándar.
V_MIN = 0.95
V_MAX = 1.05


def _iteraciones(net):
    try:
        return int(net._ppc.get("iterations"))
    except (AttributeError, TypeError, KeyError):
        return None


def modelo_a(escenario):
    """Cinco fuentes ideales en la frontera: la red tal como la usa GridMind."""
    net = cargar_red_cr(escenario, forzar_recarga=True)
    pp.runpp(net, algorithm="nr")
    return net


def modelo_b(escenario):
    """
    Nodo de referencia en la barra 50120, sin fuentes de frontera: la
    red tal como la declara el Excel.
    """
    net = cargar_red_cr(escenario, forzar_recarga=True)

    candidatos = net.gen[net.gen["bus"] == BARRA_SLACK_EXCEL].index
    if not len(candidatos):
        raise RuntimeError(
            "No hay generador en la barra {}; no se puede construir el "
            "modelo B.".format(BARRA_SLACK_EXCEL)
        )

    net.gen.at[candidatos[0], "slack"] = True
    net.ext_grid = net.ext_grid.iloc[0:0]

    pp.runpp(net, algorithm="nr")
    return net


def tabla_flujos_frontera():
    """Potencia que cruza cada interconexión en el modelo A."""
    filas = []
    for esc in ESCENARIOS:
        net = modelo_a(esc)
        for i in net.ext_grid.index:
            p = float(net.res_ext_grid.at[i, "p_mw"])
            filas.append({
                "Escenario": "CR_" + esc,
                "Interconexión": str(net.ext_grid.at[i, "name"]).strip(),
                "Barra": int(net.ext_grid.at[i, "bus"]),
                "P (MW)": round(p, 2),
                "Q (MVAr)": round(float(net.res_ext_grid.at[i, "q_mvar"]), 2),
                "Sentido": "importa" if p > 0 else "exporta",
            })
    return pd.DataFrame(filas)


def tabla_comparacion():
    """Métricas globales de cada representación, por escenario."""
    filas = []
    for esc in ESCENARIOS:
        A = modelo_a(esc)
        B = modelo_b(esc)

        for etiqueta, net, frontera in (
            ("A — 5 fuentes en frontera", A, float(A.res_ext_grid["p_mw"].abs().sum())),
            ("B — referencia en 50120", B, 0.0),
        ):
            vm = net.res_bus["vm_pu"].dropna()
            filas.append({
                "Escenario": "CR_" + esc,
                "Representación": etiqueta,
                "Iteraciones NR": _iteraciones(net),
                "Vmin (pu)": round(float(vm.min()), 4),
                "Vmax (pu)": round(float(vm.max()), 4),
                "P generada (MW)": round(float(net.res_gen["p_mw"].sum()), 2),
                "|P| en frontera (MW)": round(frontera, 2),
                "Subtensiones": int((vm < V_MIN).sum()),
                "Sobretensiones": int((vm > V_MAX).sum()),
                "Barras con resultado": int(len(vm)),
            })
    return pd.DataFrame(filas)


def tabla_diferencias():
    """Diferencia de tensión barra por barra entre ambas representaciones."""
    filas = []
    for esc in ESCENARIOS:
        A = modelo_a(esc)
        B = modelo_b(esc)

        vmA = A.res_bus["vm_pu"].dropna()
        vmB = B.res_bus["vm_pu"].dropna()
        comun = vmA.index.intersection(vmB.index)
        d = (vmA.loc[comun] - vmB.loc[comun]).abs()

        filas.append({
            "Escenario": "CR_" + esc,
            "Barras comparadas": int(len(comun)),
            "Diferencia máxima (pu)": round(float(d.max()), 4),
            "Diferencia mediana (pu)": round(float(d.median()), 4),
            "Barras con dif > 0.01 pu": int((d > 0.01).sum()),
            "Barras con dif > 0.05 pu": int((d > 0.05).sum()),
            "Barra de máxima diferencia": int(d.idxmax()),
        })
    return pd.DataFrame(filas)


def main():
    ancho = 78
    print("=" * ancho)
    print("SENSIBILIDAD A LA REPRESENTACIÓN DE LAS INTERCONEXIONES")
    print("=" * ancho)
    print()
    print("Modelo A: cinco fuentes ideales en las barras de frontera de 230 kV")
    print("          ({}).".format(", ".join(str(b) for b in BARRAS_FRONTERA)))
    print("          Es la representación que construye red_cr.py y usa GridMind.")
    print()
    print("Modelo B: nodo de referencia en la barra {}, sin fuentes de".format(
        BARRA_SLACK_EXCEL))
    print("          frontera. Es lo que declara el Excel (Bus Data, Code 3).")
    print()

    print("-" * ancho)
    print("TABLA 1 — Potencia que cruza cada interconexión (modelo A)")
    print("-" * ancho)
    t1 = tabla_flujos_frontera()
    print(t1.to_string(index=False))
    print()

    print("-" * ancho)
    print("TABLA 2 — Comparación de ambas representaciones")
    print("-" * ancho)
    t2 = tabla_comparacion()
    print(t2.to_string(index=False))
    print()

    print("-" * ancho)
    print("TABLA 3 — Diferencia de tensión barra por barra")
    print("-" * ancho)
    t3 = tabla_diferencias()
    print(t3.to_string(index=False))
    print()

    # --- Lectura de resultados ---
    print("=" * ancho)
    print("LECTURA")
    print("=" * ancho)
    for esc in ESCENARIOS:
        red = "CR_" + esc
        sub = t2[t2["Escenario"] == red]["Subtensiones"].tolist()
        print("  {}: {} subtensiones con el modelo A contra {} con el modelo B.".format(
            red, sub[0], sub[1]))
    print()
    print("  El conteo de subtensiones —la métrica que compara la validación—")
    print("  depende de la representación de frontera. Igualar esa condición")
    print("  entre GridMind y ETAP es un paso previo obligatorio: sin eso, la")
    print("  comparación mide una diferencia de modelado y no de cálculo.")
    print()

    salida = "sensibilidad_frontera.xlsx"
    with pd.ExcelWriter(salida) as xl:
        t1.to_excel(xl, sheet_name="Flujos frontera", index=False)
        t2.to_excel(xl, sheet_name="Comparacion", index=False)
        t3.to_excel(xl, sheet_name="Diferencias", index=False)
    print("Tablas exportadas a {}".format(salida))

    print()
    print("=" * ancho)
    print("MISMAS TABLAS EN MARKDOWN (para pegar en el TFG)")
    print("=" * ancho)
    for nombre, t in (("Tabla 1 — Flujos en la frontera", t1),
                      ("Tabla 2 — Comparación de representaciones", t2),
                      ("Tabla 3 — Diferencias de tensión", t3)):
        print()
        print("**{}**".format(nombre))
        print()
        print(t.to_markdown(index=False))

    return t1, t2, t3


if __name__ == "__main__":
    main()
