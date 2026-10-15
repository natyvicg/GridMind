"""
verificar_cambios.py — Verificación completa de los cambios, sin gastar API.

Corre todas las comprobaciones de una sola vez y devuelve un informe con
PASA o FALLA por cada punto, más los números concretos para revisarlos a
ojo. No requiere API key ni conexión a internet: sí requiere los
archivos Excel de la red CR.

Qué verifica
------------
  A. Los módulos importan y las 8 herramientas están registradas.
  B. run_power_flow reporta las iteraciones de Newton-Raphson.
  C. El cortocircuito calcula con datos del modelo en la red CR.
  D. El cortocircuito informa datos faltantes en las redes IEEE.
  E. La guarda de plausibilidad detecta tensiones nominales de relleno.
  F. get_overloaded_lines ahora ve los transformadores.
  G. El HTML de sesión incluye los dos contadores de iteraciones.
  H. Las cuatro pruebas y validaciones de tests/ corren y dan lo esperado.

Uso:
    python verificar_cambios.py
"""

import os
import subprocess
import sys
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

warnings.filterwarnings("ignore")

ANCHO = 74
resultados = []


def registrar(clave, titulo, ok, detalle=""):
    resultados.append({"clave": clave, "titulo": titulo, "ok": bool(ok),
                       "detalle": detalle})
    estado = "PASA " if ok else "FALLA"
    print("  [{}] {}".format(estado, detalle if detalle else titulo))


def seccion(letra, titulo):
    print()
    print("-" * ANCHO)
    print("{}. {}".format(letra, titulo))
    print("-" * ANCHO)


# ===========================================================================
seccion("A", "Módulos e inventario de herramientas")
# ===========================================================================

try:
    import datos_cortocircuito  # noqa: F401
    import tools
    from definitions import ANTHROPIC_TOOLS
    registrar("A1", "importaciones", True, "los módulos importan sin error")
except Exception as e:
    registrar("A1", "importaciones", False, "error al importar: {}".format(e))
    print("\nNo se puede continuar sin los módulos. Se detiene aquí.")
    sys.exit(1)

ESPERADAS = {
    "run_power_flow", "get_voltage_violations", "get_overloaded_lines",
    "run_short_circuit", "disconnect_line", "reconnect_line",
    "modify_load", "list_available_networks",
}
en_schema = {t["name"] for t in ANTHROPIC_TOOLS}
en_dispatcher = set(tools.TOOL_FUNCTIONS)

registrar("A2", "schema", en_schema == ESPERADAS,
          "definitions.py expone {} herramientas: {}".format(
              len(en_schema), ", ".join(sorted(en_schema))))
registrar("A3", "dispatcher", en_dispatcher == ESPERADAS,
          "tools.py despacha las mismas {} herramientas".format(len(en_dispatcher)))
registrar("A4", "reset_network fuera del agente",
          "reset_network" not in en_dispatcher and hasattr(tools, "reset_network"),
          "reset_network existe como función pero NO es herramienta del agente")

# ===========================================================================
seccion("B", "Iteraciones de Newton-Raphson en run_power_flow")
# ===========================================================================

pf_ieee = tools.execute_tool("run_power_flow", {"network": "IEEE_30"})
ok = pf_ieee.get("iterations_nr") is not None
registrar("B1", "IEEE_30", ok,
          "IEEE_30 converge en {} iteraciones NR".format(pf_ieee.get("iterations_nr")))

pf_cr = tools.execute_tool("run_power_flow", {"network": "CR_Max"})
ok = pf_cr.get("iterations_nr") is not None and pf_cr.get("converged")
registrar("B2", "CR_Max", ok,
          "CR_Max converge en {} iteraciones NR | {} barras, {} con resultado | "
          "Vmin {:.4f} Vmax {:.4f} pu".format(
              pf_cr.get("iterations_nr"), pf_cr.get("n_buses"),
              pf_cr.get("n_buses_with_result"),
              pf_cr.get("v_min_pu"), pf_cr.get("v_max_pu")))

# ===========================================================================
seccion("C", "Cortocircuito con datos del modelo en la red CR")
# ===========================================================================

for esc in ("Min", "Med", "Max"):
    red = "CR_" + esc
    tools.execute_tool("run_power_flow", {"network": red})
    cc = tools.execute_tool("run_short_circuit", {"limit": 3})
    ok = (
        "error" not in cc
        and cc.get("datos_de_maquina_del_modelo") is True
        and cc.get("n_buses_with_result") == 513
        and 0 < cc.get("ikss_max_ka", 0) < 200
        and cc.get("resultado_implausible") is not True
    )
    if ok:
        detalle = ("{}: Icc máx {:.2f} kA en {} | mediana {:.3f} kA | "
                   "{} barras | {} supuestos declarados".format(
                       red, cc["ikss_max_ka"],
                       cc["buses_mayor_corriente"][0]["nombre"],
                       cc["ikss_median_ka"], cc["n_buses_with_result"],
                       len(cc["supuestos"])))
    else:
        detalle = "{}: {}".format(red, cc.get("error", "resultado inesperado"))
    registrar("C-" + esc, red, ok, detalle)

tools.execute_tool("run_power_flow", {"network": "CR_Max"})
cc = tools.execute_tool("run_short_circuit", {"limit": 5})
ok = "correccion_de_datos_aplicada" in cc and "X Source" in cc.get("fuente_datos", "")
registrar("C4", "procedencia", ok,
          "el resultado declara la fuente y la corrección de mapeo aplicada")

bif = tools.execute_tool("run_short_circuit", {"fault_type": "2ph", "limit": 1})
razon = None
if "error" not in bif and cc.get("ikss_max_ka"):
    razon = bif["ikss_max_ka"] / cc["ikss_max_ka"]
ok = razon is not None and abs(razon - 0.8660) < 0.005
registrar("C5", "relación bifásica/trifásica", ok,
          "Icc bifásica / trifásica = {:.4f} (teoría: raíz(3)/2 = 0.8660)".format(
              razon if razon else 0))

mono = tools.execute_tool("run_short_circuit", {"fault_type": "1ph"})
ok = "error" in mono and "1ph" in mono["error"]
registrar("C6", "falla monofásica rechazada", ok,
          "la monofásica se rechaza: el modelo no trae secuencia cero")

# ===========================================================================
seccion("D", "Guarda de procedencia en redes IEEE")
# ===========================================================================

tools.execute_tool("run_power_flow", {"network": "IEEE_14"})
cc = tools.execute_tool("run_short_circuit", {})
ok = ("error" in cc and cc.get("datos_faltantes")
      and "como_proceder" in cc and "ikss_max_ka" not in cc)
registrar("D1", "informa en vez de inventar", ok,
          "IEEE_14: informa {} parámetros faltantes y NO devuelve corrientes".format(
              len(cc.get("datos_faltantes", []))))

# ===========================================================================
seccion("E", "Guarda de plausibilidad física")
# ===========================================================================

cc = tools.execute_tool("run_short_circuit",
                        {"parametros_tipicos": True, "limit": 2})
ok = (cc.get("resultado_implausible") is True
      and cc.get("datos_de_maquina_del_modelo") is False
      and "warning" in cc)
registrar("E1", "IEEE_14 con parámetros típicos", ok,
          "detecta {:.0f} kA como implausible (IEEE 14 declara barras en "
          "0.208 kV)".format(cc.get("ikss_max_ka", 0)))

tools.execute_tool("run_power_flow", {"network": "IEEE_118"})
cc = tools.execute_tool("run_short_circuit",
                        {"parametros_tipicos": True, "limit": 2})
ok = (cc.get("resultado_implausible") is not True
      and cc.get("datos_de_maquina_del_modelo") is False)
registrar("E2", "IEEE_118 con parámetros típicos", ok,
          "IEEE_118 sí da valores plausibles ({:.2f} kA) y queda rotulado "
          "como supuesto".format(cc.get("ikss_max_ka", 0)))

# ===========================================================================
seccion("F", "Sobrecargas de transformador")
# ===========================================================================

tools.execute_tool("run_power_flow", {"network": "CR_Max"})
base = tools.execute_tool("get_overloaded_lines", {})
ok = "n_overloaded_trafos" in base and "n_overloaded_elementos" in base
registrar("F1", "campos nuevos", ok,
          "operación normal: {} líneas y {} transformadores sobre 100 %".format(
              base.get("n_overloaded_total"), base.get("n_overloaded_trafos")))

# Escenario forzado: N-1 en la línea más cargada + cargas x1.3
net = tools._STATE["net"]
peor = net.res_line["loading_percent"].idxmax()
net.line.at[peor, "in_service"] = False
net.load.loc[:, "p_mw"] *= 1.3
net.load.loc[:, "q_mvar"] *= 1.3
tools.execute_tool("run_power_flow", {})
forzado = tools.execute_tool("get_overloaded_lines", {})

ok = (forzado.get("n_overloaded_total") == 0
      and forzado.get("n_overloaded_trafos", 0) > 0
      and "warning" in forzado)
detalle = ("escenario forzado (N-1 + cargas x1.3): {} líneas y {} "
           "transformadores sobrecargados, con aviso".format(
               forzado.get("n_overloaded_total"),
               forzado.get("n_overloaded_trafos")))
registrar("F2", "detecta trafos sin líneas", ok, detalle)
for t in forzado.get("overloaded_trafos", []):
    print("          {} idx {} -> {:.2f} %".format(
        t["tipo"], t["trafo_index"], t["loading_percent"]))

# Dejar la red limpia. OJO: volver a llamar run_power_flow con el mismo
# nombre de red NO recarga nada, porque _load_network devuelve la red que
# ya está en memoria, con las modificaciones incluidas. Para descartar las
# modificaciones hay que pasar por reset_network().
tools.reset_network()
tools.execute_tool("run_power_flow", {"network": "CR_Max"})

# ===========================================================================
seccion("G0", "Orden por severidad y memoria de conversación")
# ===========================================================================

tools.execute_tool("run_power_flow", {"network": "CR_Max"})
viol = tools.execute_tool("get_voltage_violations", {"limit": 20})
tipos = {v["tipo"] for v in viol["violations"]}
peor = viol["violations"][0] if viol["violations"] else {}
ok = (len(tipos) == 2
      and viol.get("top5_subtension") and viol.get("top5_sobretension")
      and all("desviacion_pu" in v for v in viol["violations"]))
registrar("G0a", "orden por severidad", ok,
          "el top 20 mezcla los dos tipos; la más severa es la barra {} "
          "({:.4f} pu, desviación {:.4f})".format(
              peor.get("bus_index"), peor.get("vm_pu", 0),
              peor.get("desviacion_pu", 0)))

corto = tools.execute_tool("get_voltage_violations", {"limit": 1})
ok = (len(corto["violations"]) == 1
      and len(corto["top5_subtension"]) == 5
      and len(corto["top5_sobretension"]) == 5
      and "nota_limite" in corto)
registrar("G0b", "top5 independientes de limit", ok,
          "con limit=1 los top5 de cada tipo siguen completos")

import agent as _agente
import inspect as _inspect
ok = "historial" in _inspect.signature(_agente.run_react_loop).parameters
registrar("G0c", "run_react_loop acepta historial", ok,
          "run_react_loop recibe el historial de la conversación")

for regla in ("MEMORIA DE LA CONVERSACIÓN", "CUANDO LA CONSULTA ES AMBIGUA",
              "SUPUESTOS Y NORMAS"):
    registrar("G0-" + regla[:12], regla, regla in _agente.SYSTEM_PROMPT,
              "regla en el system prompt: {}".format(regla.lower()))

# ===========================================================================
seccion("G", "HTML de sesión con los dos contadores")
# ===========================================================================

# main.py verifica la API key al importarse. Para esta comprobación offline
# se define un valor de relleno: no se hace ninguna llamada a la API.
os.environ.setdefault("ANTHROPIC_API_KEY", "verificacion-local-sin-api")

try:
    import tempfile

    import main as cli

    # El HTML de esta comprobación va a una carpeta temporal, para no dejar
    # sesiones de prueba mezcladas con las sesiones reales en logs/.
    cli.LOGS_DIR = Path(tempfile.mkdtemp(prefix="gridmind_verif_"))

    sesion = cli.Sesion()
    sesion.registrar(
        "Consulta de prueba para la verificación",
        {
            "final_text": "## Resultado\n\n| Parámetro | Valor |\n|---|---|\n| Vmin | 0.7521 pu |\n",
            "usage": {"input_tokens": 8000, "output_tokens": 900},
            "iterations": 2,
            "tool_calls": [{
                "name": "run_power_flow", "input": {"network": "CR_Max"},
                "result": {"network": "CR_Max", "converged": True,
                           "iterations_nr": 5},
            }],
        },
        13.6,
    )
    archivo, error = sesion.guardar_md()
    html = archivo.read_text(encoding="utf-8") if archivo else ""

    claves = ["Iteraciones agente", "Iteraciones NR", "Cómputo",
              "iteraciones del agente", "iteraciones Newton-Raphson",
              "glosario"]
    faltan = [c for c in claves if c not in html]
    registrar("G1", "HTML", not faltan and error is None,
              "HTML generado en {} con las {} etiquetas nuevas".format(
                  archivo, len(claves)) if not faltan
              else "faltan en el HTML: {}".format(faltan))
    registrar("G2", "extractor de iteraciones NR",
              cli._iteraciones_nr([{"name": "run_power_flow",
                                    "result": {"iterations_nr": 7}}]) == 7,
              "_iteraciones_nr extrae correctamente el valor de las tool_calls")

    hist = sesion.historial_para_agente()
    ok = (len(hist) == 2 and hist[0]["role"] == "user"
          and hist[1]["role"] == "assistant")
    registrar("G3", "historial", ok,
              "la sesión arma {} mensajes de historial para el agente".format(
                  len(hist)))
    n = sesion.olvidar()
    registrar("G4", "/olvidar", len(sesion.historial_para_agente()) == 0
              and len(sesion.entradas) > 0,
              "/olvidar corta el contexto ({} consulta) sin borrar el "
              "registro de la sesión".format(n))
except Exception as e:
    registrar("G1", "HTML", False, "error: {}".format(e))

# ===========================================================================
seccion("H", "Pruebas y validaciones de tests/")
# ===========================================================================

def correr(modulo, espera=None, etiqueta=None):
    proc = subprocess.run([sys.executable, "-m", modulo],
                          capture_output=True, text=True, cwd=str(RAIZ))
    salida = proc.stdout + proc.stderr
    ok = proc.returncode == 0
    if ok and espera:
        ok = espera in salida
    linea = ""
    for l in salida.splitlines():
        if "Coinciden:" in l or "TODOS LOS TESTS" in l:
            linea = l.strip()
    registrar(modulo, etiqueta or modulo, ok,
              "{}: {}".format(modulo, linea if linea else
                              ("sin errores" if ok else "falló")))
    return ok, salida


correr("tests.test_validacion_umbrales", "TODOS LOS TESTS PASARON")
correr("tests.test_cortocircuito", "TODOS LOS TESTS PASARON")
correr("tests.validar_agente", "95  (98.96%)", "validación pre-mitigación")
correr("tests.validar_agente_v2", "96  (100.0%)", "validación post-mitigación")

for nombre in ("logs/log_validacion_v1.json", "logs/log_validacion_v2.json"):
    registrar(nombre, nombre, Path(nombre).exists(),
              "{} {}".format(nombre,
                             "existe" if Path(nombre).exists() else "NO existe"))

# ===========================================================================
# Informe final
# ===========================================================================

print()
print("=" * ANCHO)
n_ok = sum(1 for r in resultados if r["ok"])
n_total = len(resultados)
print("RESULTADO: {}/{} comprobaciones pasaron".format(n_ok, n_total))
print("=" * ANCHO)

fallidas = [r for r in resultados if not r["ok"]]
if fallidas:
    print()
    print("Comprobaciones fallidas:")
    for r in fallidas:
        print("  - [{}] {}".format(r["clave"], r["detalle"] or r["titulo"]))
    print()
    print("Pegame esta lista y lo revisamos.")
    sys.exit(1)

print()
print("Todo en orden. Ninguna de estas comprobaciones usa la API.")
print("Para probar el agente en vivo:  python main.py")
sys.exit(0)
