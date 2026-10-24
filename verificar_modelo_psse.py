"""
verificar_modelo_psse.py - Compara la solucion de flujo de potencia del modelo
convertido (pandapower) con la solucion de origen (PSS/E) que trae el archivo
de SIGMA en la hoja 'Bus Data', columnas 'Voltage (pu)' y 'Angle (deg)'.

Uso (desde la carpeta del repositorio):
    python verificar_modelo_psse.py
Escribe verificacion_modelo_psse.xlsx con la comparacion barra por barra y
un resumen por escenario, e imprime el resumen en consola.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
import pandas as pd
import numpy as np
from red_cr_loader import cargar_red_cr, CR_BACKUPS

resumen = []
hojas = {}
for esc in ["Min", "Med", "Max"]:
    net = cargar_red_cr(esc)
    bus = pd.read_excel(os.path.join(RAIZ, CR_BACKUPS[esc]), sheet_name="Bus Data")
    bus["Barra"] = bus["Barra"].astype(int)
    bus = bus.set_index("Barra")
    v_psse = bus["Voltage (pu)"].astype(float)
    a_psse = bus["Angle (deg)"].astype(float)
    kv = bus["Base KV"].astype(float)
    vm = net.res_bus["vm_pu"].dropna()
    va = net.res_bus["va_degree"]
    comunes = [b for b in vm.index if b in v_psse.index]
    df = pd.DataFrame({
        "barra": comunes,
        "kv": kv.loc[comunes].values,
        "v_pandapower": vm.loc[comunes].values,
        "v_psse": v_psse.loc[comunes].values,
        "ang_pandapower": va.loc[comunes].values,
        "ang_psse": a_psse.loc[comunes].values,
    })
    df["diferencia"] = df["v_pandapower"] - df["v_psse"]
    df["abs"] = df["diferencia"].abs()
    df["dif_angulo"] = ((df["ang_pandapower"] - df["ang_psse"] + 180) % 360) - 180
    df["abs_angulo"] = df["dif_angulo"].abs()
    df = df.sort_values("abs", ascending=False)
    hojas[esc] = df
    alta = df[df.kv >= 138]
    fila = {
        "escenario": esc,
        "barras comparadas": len(df),
        "dif. maxima (pu)": round(df["abs"].max(), 4),
        "barra de la dif. maxima": int(df.iloc[0]["barra"]),
        "dif. mediana (pu)": round(df["abs"].median(), 4),
        "barras con dif. > 0,01 pu": int((df["abs"] > 0.01).sum()),
        "dif. maxima 230/138 kV (pu)": round(alta["abs"].max(), 4),
        "dif. maxima de angulo (grados)": round(df["abs_angulo"].max(), 3),
        "dif. mediana de angulo (grados)": round(df["abs_angulo"].median(), 3),
        "pandapower: V min": round(df.v_pandapower.min(), 4),
        "pandapower: V max": round(df.v_pandapower.max(), 4),
        "PSS/E: V min": round(df.v_psse.min(), 4),
        "PSS/E: V max": round(df.v_psse.max(), 4),
        "pandapower: sub/sob 0,95-1,05": "%d / %d" % ((df.v_pandapower < 0.95).sum(), (df.v_pandapower > 1.05).sum()),
        "PSS/E: sub/sob 0,95-1,05": "%d / %d" % ((df.v_psse < 0.95).sum(), (df.v_psse > 1.05).sum()),
    }
    resumen.append(fila)

res = pd.DataFrame(resumen)
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
print(res.T.to_string())
salida = os.path.join(RAIZ, "verificacion_modelo_psse.xlsx")
with pd.ExcelWriter(salida) as w:
    res.to_excel(w, sheet_name="Resumen", index=False)
    for esc, df in hojas.items():
        df.to_excel(w, sheet_name=esc, index=False)
print("\nEscrito:", salida)
