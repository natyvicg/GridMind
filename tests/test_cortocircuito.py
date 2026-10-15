"""
test_cortocircuito.py — Verifica la herramienta de cortocircuito y la
capa de datos que la alimenta.

No requiere API key ni conexión a internet. Sí requiere los archivos de
la red CR (los backups _Backup_*.xlsx o los originales Base_CR_*.xlsx).

Casos de prueba
---------------
  1. El Excel de la red CR tiene la impedancia de máquina en la columna
     'X Source (pu)' y ceros en 'Xtran (pu)', que es la que lee red_cr.py.
  2. El orden de net.gen coincide barra por barra con el orden del Excel
     en los tres escenarios (condición para poder remapear).
  3. Tras preparar la red, el diagnóstico pasa y el cálculo produce
     resultado en las 513 barras energizadas.
  4. En una red IEEE la herramienta informa los datos faltantes en vez
     de inventarlos.
  5. Con parametros_tipicos sobre IEEE 14, la guarda de plausibilidad
     detecta que las tensiones nominales del modelo son marcadores de
     posición.
  6. Los resultados se presentan con el nombre real de la subestación.

Uso:
    python -m tests.test_cortocircuito
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

import pandas as pd  # noqa: E402

import datos_cortocircuito as dcc  # noqa: E402
from red_cr_loader import cargar_red_cr  # noqa: E402
from tools import execute_tool  # noqa: E402

ESCENARIOS = ("Min", "Med", "Max")
LINEA = "=" * 70


def _saltar_si_falta_excel():
    try:
        dcc._ruta_excel_cr("Max")
        return False
    except FileNotFoundError:
        print("  Archivos de la red CR no disponibles: se salta el caso.")
        return True


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 1: la impedancia de máquina está en 'X Source', no en 'Xtran'")
print(LINEA)

if not _saltar_si_falta_excel():
    ruta = dcc._ruta_excel_cr("Max")
    crudo = pd.read_excel(ruta, sheet_name=dcc.HOJA_GENERADORES, header=None)
    encabezados = crudo.iloc[0].tolist()

    assert str(encabezados[dcc.COL_X_SOURCE]).strip().lower().startswith("x source"), \
        "FALLO: la columna {} no es 'X Source'".format(dcc.COL_X_SOURCE)

    x_source = pd.to_numeric(crudo.iloc[1:, dcc.COL_X_SOURCE], errors="coerce").dropna()
    x_tran = pd.to_numeric(crudo.iloc[1:, 12], errors="coerce").dropna()

    print("  columna {}: '{}' → {} valores, rango {:.4f} a {:.4f} pu".format(
        dcc.COL_X_SOURCE, str(encabezados[dcc.COL_X_SOURCE]).strip(),
        len(x_source), x_source.min(), x_source.max()))
    print("  columna 12: '{}' → {} valores, todos en cero: {}".format(
        str(encabezados[12]).strip(), len(x_tran), bool((x_tran == 0).all())))

    assert (x_source > 0).all(), "FALLO: 'X Source' debería tener valores positivos"
    assert (x_tran == 0).all(), "FALLO: se esperaba 'Xtran' en cero en este modelo"
    print("  OK\n")


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 2: alineación barra por barra entre net.gen y el Excel")
print(LINEA)

if not _saltar_si_falta_excel():
    for esc in ESCENARIOS:
        net = cargar_red_cr(esc)
        imp, archivo = dcc._leer_impedancias_cr(esc)
        barras_net = [int(b) for b in net.gen["bus"].tolist()]
        assert len(imp) == len(net.gen), \
            "FALLO {}: {} filas en el Excel y {} generadores".format(
                esc, len(imp), len(net.gen))
        assert barras_net == imp["barra"].tolist(), \
            "FALLO {}: el orden de las barras no coincide".format(esc)
        print("  {}: {} generadores alineados ({})".format(
            esc, len(net.gen), archivo))
    print("  OK\n")


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 3: la red CR queda apta y el cálculo produce resultados")
print(LINEA)

if not _saltar_si_falta_excel():
    for esc in ESCENARIOS:
        red = "CR_" + esc
        pf = execute_tool("run_power_flow", {"network": red})
        assert pf.get("converged"), "FALLO {}: el flujo no convergió".format(red)

        cc = execute_tool("run_short_circuit", {"limit": 3})
        assert "error" not in cc, "FALLO {}: {}".format(red, cc.get("error"))
        assert cc["datos_de_maquina_del_modelo"] is True, \
            "FALLO {}: debería usar datos del modelo".format(red)
        assert cc["n_buses_with_result"] == 513, \
            "FALLO {}: se esperaban 513 barras con resultado, hubo {}".format(
                red, cc["n_buses_with_result"])
        assert 0 < cc["ikss_max_ka"] < 200, \
            "FALLO {}: Icc máxima fuera de rango razonable".format(red)
        assert cc.get("resultado_implausible") is not True, \
            "FALLO {}: el resultado se marcó implausible".format(red)

        print("  {}: NR {} iter | Icc máx {:.2f} kA | mediana {:.3f} kA | "
              "{} barras".format(
                  red, pf.get("iterations_nr"), cc["ikss_max_ka"],
                  cc["ikss_median_ka"], cc["n_buses_with_result"]))
    print("  OK\n")


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 4: en una red IEEE se informan los datos faltantes")
print(LINEA)

execute_tool("run_power_flow", {"network": "IEEE_14"})
cc = execute_tool("run_short_circuit", {})

assert "error" in cc, "FALLO: debería devolver error de datos faltantes"
assert "datos_faltantes" in cc and cc["datos_faltantes"], \
    "FALLO: debería nombrar los parámetros faltantes"
assert "como_proceder" in cc, "FALLO: debería indicar cómo proceder"
assert "ikss_max_ka" not in cc, "FALLO: no debería devolver corrientes"

print("  parámetros faltantes reportados: {}".format(len(cc["datos_faltantes"])))
for f in cc["datos_faltantes"]:
    print("    - {}".format(f))
print("  OK\n")


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 5: guarda de plausibilidad con parámetros típicos en IEEE 14")
print(LINEA)

cc = execute_tool("run_short_circuit", {"parametros_tipicos": True, "limit": 2})

assert "error" not in cc, "FALLO: con parametros_tipicos debería calcular"
assert cc["datos_de_maquina_del_modelo"] is False, \
    "FALLO: debería rotularse como no proveniente del modelo"
assert "warning" in cc, "FALLO: debería traer warning"
assert cc.get("resultado_implausible") is True, \
    "FALLO: IEEE 14 declara barras en 0.208 kV; debería marcarse implausible"
assert cc["supuestos"], "FALLO: debería enumerar los supuestos"

print("  Icc máx calculada: {:.0f} kA (implausible, como se espera)".format(
    cc["ikss_max_ka"]))
print("  supuestos declarados: {}".format(len(cc["supuestos"])))
print("  OK\n")


# ---------------------------------------------------------------------------

print(LINEA)
print("Test 6: los resultados traen el nombre real de la subestación")
print(LINEA)

if not _saltar_si_falta_excel():
    mapa = dcc.mapa_nombres_cr("Max")
    assert mapa, "FALLO: el mapa de nombres no debería estar vacío"

    execute_tool("run_power_flow", {"network": "CR_Max"})
    cc = execute_tool("run_short_circuit", {"limit": 5})

    con_nombre = [b for b in cc["buses_mayor_corriente"] if b.get("nombre")]
    assert len(con_nombre) == len(cc["buses_mayor_corriente"]), \
        "FALLO: todas las barras del top deberían tener nombre"
    assert not con_nombre[0]["nombre"].isdigit(), \
        "FALLO: el nombre no debería ser el número de barra"

    print("  {} nombres de barra leídos del Excel".format(len(mapa)))
    for b in cc["buses_mayor_corriente"]:
        print("    {:>7}  {:<12} {:>6.1f} kV  {:>7.2f} kA".format(
            b["bus_index"], b["nombre"], b["vn_kv"], b["ikss_ka"]))
    print("  OK\n")


print(LINEA)
print("TODOS LOS TESTS PASARON")
print(LINEA)
