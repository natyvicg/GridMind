"""
tools.py — Herramientas PandaPower que GridMind expone al LLM.

Funciones disponibles:
    run_power_flow          Carga red y ejecuta flujo de potencia Newton-Raphson.
    get_voltage_violations  Detecta barras con tensión fuera de rango operacional.
    get_overloaded_lines    Detecta líneas con cargabilidad excesiva.
    run_short_circuit       Corriente de cortocircuito trifásica (IEC 60909).
    disconnect_line         Desconecta una línea (simulación N-1).
    reconnect_line          Reconecta una línea previamente desconectada.
    modify_load             Modifica P y/o Q de una carga existente.
    reset_network           Limpia el estado interno (descarga la red actual).

Estado persistente:
    El módulo mantiene un diccionario _STATE con la red cargada. Esto evita
    que cada llamada a run_power_flow reconstruya la red desde cero, lo cual
    perdería cualquier modificación previa (líneas desconectadas, cargas
    alteradas, etc.).

Dispatcher:
    execute_tool(name, input) despacha por nombre. Para agregar herramientas
    nuevas: definir la función + agregarla a TOOL_FUNCTIONS.

Validación de inputs:
    get_voltage_violations valida umbrales para prevenir confusión entre
    umbrales operacionales (0.95/1.05 estándar) y valores observados.
    Emite warning blando si los umbrales son inusuales, error duro si
    v_min >= v_max.

Procedencia de datos en cortocircuito:
    run_short_circuit no calcula si la red carece de los parámetros que
    IEC 60909 requiere: informa cuáles faltan y no inventa ninguno. Si
    el usuario pide calcular igual con parámetros típicos, el resultado
    se devuelve rotulado como basado en supuestos declarados y no en el
    modelo. La lógica de datos vive en datos_cortocircuito.py.
"""

import math
import pandapower as pp
import pandapower.networks as pn
import pandapower.shortcircuit as pp_sc

from red_cr_loader import cargar_red_cr, limpiar_cache as _limpiar_cache_cr
from datos_cortocircuito import (
    preparar_red_cr as _preparar_cc_cr,
    aplicar_parametros_tipicos as _parametros_cc_tipicos,
    diagnosticar as _diagnosticar_cc,
    ENDTEMP_MIN_DEGREE as _ENDTEMP_MIN,
    mapa_nombres_cr,
)


# Corriente de cortocircuito por encima de la cual el resultado se
# considera físicamente implausible en una red de transmisión. Sirve de
# guarda: algunas redes de prueba traen tensiones nominales que son solo
# marcadores de posición (IEEE 14 tiene barras declaradas en 0.208 kV),
# y con esas tensiones cualquier potencia de falla produce corrientes
# absurdas. Ver run_short_circuit.
ICC_IMPLAUSIBLE_KA = 200.0


# ---------------------------------------------------------------------------
# Catálogo de redes disponibles
# ---------------------------------------------------------------------------

AVAILABLE_NETWORKS = {
    # --- Redes estándar IEEE (incluidas en pandapower.networks) ---
    "IEEE_4": {
        "fuente": "pandapower", "pp_func": "case4gs",
        "descripcion": "IEEE 4 barras (Grainger & Stevenson). Red mínima de prueba.",
    },
    "IEEE_5": {
        "fuente": "pandapower", "pp_func": "case5",
        "descripcion": "IEEE 5 barras. Red didáctica básica.",
    },
    "IEEE_6": {
        "fuente": "pandapower", "pp_func": "case6ww",
        "descripcion": "IEEE 6 barras (Wood & Wollenberg). Red didáctica.",
    },
    "IEEE_9": {
        "fuente": "pandapower", "pp_func": "case9",
        "descripcion": "IEEE 9 barras (WSCC). Red clásica de transmisión.",
    },
    "IEEE_14": {
        "fuente": "pandapower", "pp_func": "case14",
        "descripcion": "IEEE 14 barras. Red estándar académica de referencia.",
    },
    "IEEE_24_RTS": {
        "fuente": "pandapower", "pp_func": "case24_ieee_rts",
        "descripcion": "IEEE 24 barras (Reliability Test System). Planificación de confiabilidad.",
    },
    "IEEE_30": {
        "fuente": "pandapower", "pp_func": "case30",
        "descripcion": "IEEE 30 barras. Red mediana de transmisión.",
    },
    "IEEE_33_BW": {
        "fuente": "pandapower", "pp_func": "case33bw",
        "descripcion": "IEEE 33 barras (Baran-Wu). Red de distribución radial.",
    },
    "IEEE_39": {
        "fuente": "pandapower", "pp_func": "case39",
        "descripcion": "IEEE 39 barras (New England). Red de transmisión con 10 generadores.",
    },
    "IEEE_57": {
        "fuente": "pandapower", "pp_func": "case57",
        "descripcion": "IEEE 57 barras. Red mediana-grande de transmisión.",
    },
    "IEEE_89_PEGASE": {
        "fuente": "pandapower", "pp_func": "case89pegase",
        "descripcion": "89 barras (PEGASE). Red europea de transmisión.",
    },
    "IEEE_118": {
        "fuente": "pandapower", "pp_func": "case118",
        "descripcion": "IEEE 118 barras. Red grande de transmisión, benchmark clásico.",
    },
    "IEEE_145": {
        "fuente": "pandapower", "pp_func": "case145",
        "descripcion": "IEEE 145 barras. Red grande con múltiples niveles de tensión.",
    },
    "IEEE_200": {
        "fuente": "pandapower", "pp_func": "case_illinois200",
        "descripcion": "200 barras (Illinois). Red grande de transmisión.",
    },
    "IEEE_300": {
        "fuente": "pandapower", "pp_func": "case300",
        "descripcion": "IEEE 300 barras. Red muy grande, prueba de escalabilidad.",
    },
    # --- Redes Costa Rica (desde archivos Excel) ---
    "CR_Min": {
        "fuente": "cr", "escenario": "Min",
        "descripcion": "Red de Costa Rica (524 barras), demanda mínima (marzo 2023).",
    },
    "CR_Med": {
        "fuente": "cr", "escenario": "Med",
        "descripcion": "Red de Costa Rica (524 barras), demanda media (marzo 2023).",
    },
    "CR_Max": {
        "fuente": "cr", "escenario": "Max",
        "descripcion": "Red de Costa Rica (524 barras), demanda máxima (marzo 2023).",
    },
}


# ---------------------------------------------------------------------------
# Estado persistente entre llamadas
# ---------------------------------------------------------------------------
# Sin esto, cada llamada del agente a run_power_flow reconstruiría la red
# desde cero, perdiendo toda modificación previa (líneas desconectadas,
# cargas alteradas, etc.).

_STATE = {
    "net": None,                   # pp.Network actualmente cargada
    "current_network_name": None,  # Clave del catálogo (ej. "IEEE_14", "CR_Min")
    "endtemp_asumida": False,      # True si endtemp_degree se rellenó con el supuesto
}


def _load_network(network_name):
    """
    Carga la red solicitada. Si ya estaba cargada, no hace nada. Cambiar de
    red descarta cualquier modificación previa.
    """
    if network_name not in AVAILABLE_NETWORKS:
        raise ValueError(
            "Red desconocida: {!r}. Llame list_available_networks para ver "
            "las opciones disponibles.".format(network_name)
        )

    if _STATE["current_network_name"] == network_name and _STATE["net"] is not None:
        return _STATE["net"]

    info = AVAILABLE_NETWORKS[network_name]

    if info["fuente"] == "pandapower":
        # Carga genérica: busca la función por nombre en pandapower.networks
        func = getattr(pn, info["pp_func"], None)
        if func is None:
            raise ValueError(
                "Función pandapower.networks.{} no encontrada. "
                "Verifique la versión de PandaPower.".format(info["pp_func"])
            )
        net = func()
    elif info["fuente"] == "cr":
        net = cargar_red_cr(info["escenario"])
    else:
        raise ValueError("Tipo de fuente desconocido: {}".format(info["fuente"]))

    _STATE["net"] = net
    _STATE["current_network_name"] = network_name
    _STATE["endtemp_asumida"] = False
    return net


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(x):
    """Convierte a float, mapeando NaN/None a None (para serialización JSON)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


def _iteraciones_nr(net):
    """
    Devuelve el número de iteraciones que le tomó converger a
    Newton-Raphson, o None si PandaPower no lo expuso.

    PandaPower guarda el dato en net._ppc["iterations"]. Es un atributo
    interno, así que se lee de forma defensiva: si una versión futura lo
    mueve o lo renombra, la herramienta devuelve None en vez de fallar.
    """
    try:
        ppc = getattr(net, "_ppc", None)
        if not ppc:
            return None
        it = ppc.get("iterations")
        return int(it) if it is not None else None
    except Exception:
        return None



def _nombres_barras():
    """
    Devuelve {índice de barra: nombre de subestación} para presentación.
    Solo aplica a las redes CR: lee la hoja 'Bus Data' del Excel con el
    mismo mapa que usa run_short_circuit. En las redes IEEE el índice es
    el único identificador, así que devuelve un dict vacío. No modifica
    la red; si el Excel no está disponible devuelve un dict vacío.
    """
    red = _STATE.get("current_network_name") or ""
    if not red.startswith("CR_"):
        return {}
    try:
        return mapa_nombres_cr(red.split("_", 1)[1]) or {}
    except Exception:
        return {}

def _net_or_error():
    if _STATE["net"] is None:
        return None, {
            "error": "No hay red cargada. Llame run_power_flow primero con el "
                     "parámetro network indicando una de: " + ", ".join(AVAILABLE_NETWORKS)
        }
    return _STATE["net"], None


# ---------------------------------------------------------------------------
# 1. run_power_flow
# ---------------------------------------------------------------------------

def run_power_flow(network=None):
    """
    Carga (si hace falta) la red y corre flujo de potencia Newton-Raphson.
    Devuelve un resumen con métricas globales: convergencia, Vmin, Vmax,
    carga máxima de líneas y trafos.
    """
    if network is None:
        network = _STATE["current_network_name"] or "IEEE_14"

    try:
        net = _load_network(network)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    try:
        pp.runpp(net, algorithm="nr")
    except pp.LoadflowNotConverged as e:
        return {
            "network": network,
            "converged": False,
            "error": "Flujo de potencia no convergió: {}".format(e),
        }
    except Exception as e:
        return {
            "network": network,
            "converged": False,
            "error": "Error en runpp: {}".format(e),
        }

    # Filtrar NaN: en la red CR hay 11 barras sin resultado por despacho
    # operativo (3 unidades no despachadas + 8 devanados terciarios
    # desactivados). En IEEE 14 normalmente no hay NaN, pero el filtro
    # es seguro en ambos casos.
    vm_pu = net.res_bus["vm_pu"].dropna()

    res = {
        "network": network,
        "converged": bool(getattr(net, "converged", True)),
        "iterations_nr": _iteraciones_nr(net),
        "n_buses": int(len(net.bus)),
        "n_buses_with_result": int(len(vm_pu)),
        "n_lines": int(len(net.line)),
        "n_trafos": int(len(net.trafo) + len(net.trafo3w)),
        "v_min_pu": _safe_float(vm_pu.min()) if len(vm_pu) else None,
        "v_max_pu": _safe_float(vm_pu.max()) if len(vm_pu) else None,
    }

    if not net.res_line.empty:
        loading = net.res_line["loading_percent"].dropna()
        res["max_line_loading_percent"] = (
            _safe_float(loading.max()) if len(loading) else None
        )

    if not net.res_trafo.empty:
        loading = net.res_trafo["loading_percent"].dropna()
        res["max_trafo_loading_percent"] = (
            _safe_float(loading.max()) if len(loading) else None
        )

    return res


# ---------------------------------------------------------------------------
# 2. get_voltage_violations
# ---------------------------------------------------------------------------

def get_voltage_violations(v_min=0.95, v_max=1.05, limit=20):
    """
    Devuelve las barras cuya tensión está fuera de [v_min, v_max].

    Orden del resultado
    -------------------
    `violations` va ordenada por DESVIACIÓN ABSOLUTA respecto al umbral
    violado, de mayor a menor, mezclando subtensiones y sobretensiones.
    Una barra en 1.2474 pu (desviación 0.1974 sobre el límite superior)
    aparece antes que una en 0.9363 pu (desviación 0.0137 bajo el
    inferior), que es lo que significa "más severa".

    La versión anterior concatenaba primero todas las subtensiones y
    después todas las sobretensiones. Con `limit` aplicado sobre una red
    con muchas subtensiones, eso escondía las sobretensiones severas: en
    la red CR llegaban a quedar fuera 10 de las 11 sobretensiones, todas
    más severas que la última subtensión listada.

    Garantías independientes de `limit`
    -----------------------------------
      - `n_subtension` y `n_sobretension`: conteos completos, sin recortar.
      - `top5_subtension` y `top5_sobretension`: las 5 peores de cada
        tipo, SIEMPRE presentes. Aunque `limit` sea 1, ninguna violación
        severa queda invisible.

    Cada fila incluye `desviacion_pu`, para que el orden sea verificable.

    Validación de umbrales:
      - v_min y v_max deben ser umbrales OPERACIONALES, no valores
        observados. Defaults estándar: 0.95 y 1.05.
      - Si v_min >= v_max → error.
      - Si v_min < 0.85 o v_max > 1.15 → se computa igual pero se incluye
        un warning para que el LLM detecte que probablemente copió un valor
        observado en lugar del umbral estándar.
    """
    net, err = _net_or_error()
    if err:
        return err

    if net.res_bus.empty:
        return {"error": "No hay resultados de flujo. Llame run_power_flow primero."}

    # --- Validación dura: umbrales invertidos o iguales ---
    if v_min >= v_max:
        return {
            "error": (
                "Umbrales inválidos: v_min ({}) debe ser menor que v_max ({}). "
                "Para análisis estándar use v_min=0.95 y v_max=1.05.".format(v_min, v_max)
            )
        }

    # --- Warning blando: umbrales fuera del rango razonable ---
    warnings = []
    if v_min < 0.85:
        warnings.append(
            "v_min={} es inusualmente bajo. El umbral OPERACIONAL estándar es 0.95. "
            "¿Está usando un valor observado por error? Si quiere el rango estándar, "
            "omita el parámetro v_min.".format(v_min)
        )
    if v_max > 1.15:
        warnings.append(
            "v_max={} es inusualmente alto. El umbral OPERACIONAL estándar es 1.05. "
            "Recuerde: v_max es un UMBRAL contra el que se compara, no el Vmax "
            "OBSERVADO en run_power_flow. Si quiere el rango estándar, omita el "
            "parámetro v_max.".format(v_max)
        )

    vm = net.res_bus["vm_pu"].dropna()

    bajas = vm[vm < v_min].sort_values()
    altas = vm[vm > v_max].sort_values(ascending=False)

    # Nombres de subestación (solo presentación, redes CR): el mismo mapa
    # del Excel que usa run_short_circuit.
    nombres = _nombres_barras()

    def _fila(idx, val, tipo):
        desviacion = (v_min - val) if tipo == "subtension" else (val - v_max)
        fila = {
            "bus_index": int(idx) if isinstance(idx, (int, float)) else idx,
            "vm_pu": _safe_float(val),
            "tipo": tipo,
            "desviacion_pu": _safe_float(round(float(desviacion), 5)),
        }
        nombre = nombres.get(int(idx)) if isinstance(idx, (int, float)) else None
        if nombre:
            fila["nombre"] = nombre
        return fila

    filas_bajas = [_fila(i, v, "subtension") for i, v in bajas.items()]
    filas_altas = [_fila(i, v, "sobretension") for i, v in altas.items()]

    # Severidad real: desviación absoluta respecto al umbral violado.
    por_severidad = sorted(
        filas_bajas + filas_altas,
        key=lambda f: f["desviacion_pu"] or 0.0,
        reverse=True,
    )

    resultado = {
        "network": _STATE["current_network_name"],
        "v_min_threshold": v_min,
        "v_max_threshold": v_max,
        "n_violations_total": len(por_severidad),
        "n_subtension": int(len(bajas)),
        "n_sobretension": int(len(altas)),
        "limit_applied": limit,
        "orden": (
            "por desviación absoluta respecto al umbral violado, de mayor "
            "a menor, mezclando subtensiones y sobretensiones"
        ),
        "violations": por_severidad[:limit],
        "top5_subtension": filas_bajas[:5],
        "top5_sobretension": filas_altas[:5],
    }

    if len(por_severidad) > limit:
        resultado["nota_limite"] = (
            "La lista `violations` está recortada a {} de {} violaciones. "
            "Los conteos por tipo y las listas top5_subtension y "
            "top5_sobretension son completos y no dependen de este "
            "recorte.".format(limit, len(por_severidad))
        )

    if warnings:
        resultado["warning"] = " | ".join(warnings)
    return resultado


# ---------------------------------------------------------------------------
# 3. get_overloaded_lines
# ---------------------------------------------------------------------------

def get_overloaded_lines(loading_threshold=100.0, limit=20):
    """
    Devuelve los elementos cuya cargabilidad supera el umbral (en %),
    ordenados de mayor a menor carga. `limit` recorta para no inflar
    contexto.

    Cubre líneas Y transformadores. La distinción importa: la red de
    Costa Rica tiene 137 líneas y 256 transformadores (106 de dos
    devanados y 150 de tres), así que revisar solo líneas dejaría fuera
    a la mayoría de los elementos serie de la red. Una contingencia que
    sobrecarga un transformador sin sobrecargar ninguna línea es un caso
    real, no hipotético.

    Los conteos se devuelven SEPARADOS por tipo de elemento:
      - n_overloaded_total: solo líneas (semántica histórica, se
        mantiene por compatibilidad con la batería de validación).
      - n_overloaded_trafos: transformadores de dos y tres devanados.
      - n_overloaded_elementos: la suma de ambos.

    Si hay transformadores sobrecargados pero ninguna línea, el
    resultado incluye un warning, para que la ausencia de líneas
    sobrecargadas no se reporte como ausencia de sobrecargas.
    """
    net, err = _net_or_error()
    if err:
        return err

    if net.res_line.empty and net.res_trafo.empty:
        return {"error": "No hay resultados de flujo. Llame run_power_flow primero."}

    # --- Líneas ---
    filas = []
    if not net.res_line.empty:
        loading = net.res_line["loading_percent"].dropna()
        sobrecargadas = loading[loading > loading_threshold].sort_values(ascending=False)
        for line_idx, lp in sobrecargadas.items():
            from_bus = net.line.at[line_idx, "from_bus"]
            to_bus = net.line.at[line_idx, "to_bus"]
            filas.append({
                "line_index": int(line_idx),
                "from_bus": int(from_bus) if not math.isnan(float(from_bus)) else None,
                "to_bus": int(to_bus) if not math.isnan(float(to_bus)) else None,
                "loading_percent": _safe_float(lp),
            })

    # --- Transformadores de dos y tres devanados ---
    trafos = []
    for tabla_res, tabla_el, tipo, buses in (
        ("res_trafo", "trafo", "trafo_2w", ("hv_bus", "lv_bus")),
        ("res_trafo3w", "trafo3w", "trafo_3w", ("hv_bus", "mv_bus", "lv_bus")),
    ):
        res = getattr(net, tabla_res, None)
        if res is None or res.empty or "loading_percent" not in res.columns:
            continue
        el = getattr(net, tabla_el)
        carga = res["loading_percent"].dropna()
        for idx, lp in carga[carga > loading_threshold].sort_values(ascending=False).items():
            fila = {
                "trafo_index": int(idx),
                "tipo": tipo,
                "loading_percent": _safe_float(lp),
            }
            for campo in buses:
                if campo in el.columns:
                    valor = el.at[idx, campo]
                    try:
                        fila[campo] = int(valor)
                    except (TypeError, ValueError):
                        fila[campo] = None
            trafos.append(fila)

    trafos.sort(key=lambda f: f["loading_percent"] or 0.0, reverse=True)

    resultado = {
        "network": _STATE["current_network_name"],
        "loading_threshold_percent": loading_threshold,
        "n_overloaded_total": len(filas),
        "n_overloaded_trafos": len(trafos),
        "n_overloaded_elementos": len(filas) + len(trafos),
        "limit_applied": limit,
        "overloaded_lines": filas[:limit],
        "overloaded_trafos": trafos[:limit],
    }

    if trafos and not filas:
        resultado["warning"] = (
            "No hay líneas sobrecargadas, pero SÍ hay {} transformador(es) "
            "por encima del {} %. NO reporte que la red está sin sobrecargas: "
            "informe las sobrecargas de transformador, que son igual de "
            "relevantes desde el punto de vista térmico.".format(
                len(trafos), loading_threshold
            )
        )

    return resultado



# ---------------------------------------------------------------------------
# 4. run_short_circuit
# ---------------------------------------------------------------------------

def run_short_circuit(fault_type="3ph", case="max", limit=20,
                      s_sc_interconexion_mva=None, parametros_tipicos=False):
    """
    Calcula la corriente de cortocircuito según IEC 60909 sobre la red
    cargada. Devuelve la corriente inicial simétrica Ik" (ikss_ka) por
    barra, más los extremos y las barras de mayor corriente.

    Procedencia de datos (regla dura)
    ---------------------------------
    El cálculo requiere la impedancia de las fuentes, que el flujo de
    carga no usa. La red de Costa Rica la trae del modelo PSS/E de
    origen. Las redes de prueba IEEE no la traen: se publicaron como
    casos de flujo de carga y ese parámetro nunca formó parte de ellas.

    Si la red no tiene los datos, esta herramienta NO inventa valores:
    devuelve un error nombrando exactamente qué falta. Solo si el
    usuario pide explícitamente parametros_tipicos=True se calcula con
    valores de literatura, y en ese caso el resultado se rotula como
    basado en supuestos, con un warning.

    Requiere haber ejecutado run_power_flow previamente (la red debe
    estar cargada).
    """
    net, err = _net_or_error()
    if err:
        return err

    red = _STATE["current_network_name"]

    if fault_type not in ("3ph", "2ph"):
        return {
            "error": (
                "Tipo de falla no soportado: {!r}. Use '3ph' (trifásica, "
                "la del caso base de IEC 60909) o '2ph' (bifásica). Las "
                "fallas monofásicas requieren datos de secuencia cero que "
                "los modelos disponibles no incluyen.".format(fault_type)
            )
        }

    if case not in ("max", "min"):
        return {
            "error": (
                "Caso no soportado: {!r}. Use 'max' (corriente máxima de "
                "cortocircuito) o 'min' (mínima).".format(case)
            )
        }

    # --- Preparación de datos según la red ---
    supuestos = []
    correccion = None
    datos_del_modelo = True
    nombres = {}

    if red and red.startswith("CR_"):
        escenario = red.split("_", 1)[1]
        kwargs = {}
        if s_sc_interconexion_mva is not None:
            kwargs["s_sc_interconexion_mva"] = float(s_sc_interconexion_mva)
        try:
            net, informe = _preparar_cc_cr(net, escenario, **kwargs)
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            return {
                "error": (
                    "No se pudieron preparar los datos de cortocircuito de "
                    "{}: {}".format(red, e)
                )
            }
        fuente = informe["fuente_xdss"]
        supuestos = list(informe["supuestos"])
        correccion = informe["correccion_de_mapeo"]
        nombres = informe.get("nombres_barras") or {}
    else:
        diagnostico = _diagnosticar_cc(net)
        if diagnostico["apta"]:
            fuente = "parámetros de cortocircuito presentes en el modelo"
        elif not parametros_tipicos:
            return {
                "error": (
                    "La red {} no contiene los parámetros que requiere el "
                    "cálculo de cortocircuito. Los casos de prueba IEEE se "
                    "publicaron como benchmarks de flujo de carga y no "
                    "incluyen impedancias de fuente.".format(red)
                ),
                "datos_faltantes": diagnostico["faltantes"],
                "como_proceder": (
                    "Para un cálculo con datos reales, use una de las redes "
                    "de Costa Rica (CR_Min, CR_Med, CR_Max), cuyo modelo de "
                    "origen sí trae la impedancia de las 108 máquinas. Si "
                    "aun así desea un cálculo indicativo con parámetros "
                    "típicos de literatura, invoque esta herramienta con "
                    "parametros_tipicos=true; el resultado quedará rotulado "
                    "como basado en supuestos y no en el modelo."
                ),
            }
        else:
            net, informe = _parametros_cc_tipicos(net)
            fuente = informe["fuente_xdss"]
            supuestos = list(informe["supuestos"])
            datos_del_modelo = False

    # --- Caso mínimo: el modelo no distingue Ssc mínima de máxima ---
    if case == "min" and len(net.ext_grid):
        if "s_sc_max_mva" in net.ext_grid.columns:
            net.ext_grid["s_sc_min_mva"] = net.ext_grid["s_sc_max_mva"]
            net.ext_grid["rx_min"] = net.ext_grid["rx_max"]
            supuestos.append(
                "Caso mínimo: se usa la misma potencia de cortocircuito de "
                "red externa que en el caso máximo, porque el modelo no "
                "distingue entre ambas condiciones."
            )

    # --- Caso mínimo: temperatura final de conductor ---
    # IEC 60909 corrige la resistencia de las líneas a la temperatura que
    # alcanzan al final del cortocircuito y pandapower exige el dato
    # (net.line.endtemp_degree) en el caso mínimo. Ningún modelo lo trae:
    # se asume un valor declarado y se informa como supuesto.
    if case == "min" and len(net.line):
        if "endtemp_degree" not in net.line.columns:
            net.line["endtemp_degree"] = float("nan")
        faltan = net.line["endtemp_degree"].isna()
        if faltan.any():
            net.line.loc[faltan, "endtemp_degree"] = float(_ENDTEMP_MIN)
            _STATE["endtemp_asumida"] = True
        if _STATE["endtemp_asumida"]:
            supuestos.append(
                "Caso mínimo: temperatura final de conductor de {:.0f} °C "
                "para las líneas, usada para corregir su resistencia según "
                "IEC 60909 (el modelo no contiene el dato)."
                .format(_ENDTEMP_MIN)
            )

    # --- Cálculo ---
    try:
        pp_sc.calc_sc(net, fault=fault_type, case=case)
    except Exception as e:
        return {
            "error": "Error en el cálculo de cortocircuito: {}".format(e)
        }

    if net.res_bus_sc.empty or "ikss_ka" not in net.res_bus_sc.columns:
        return {"error": "El cálculo de cortocircuito no produjo resultados."}

    ik = net.res_bus_sc["ikss_ka"].dropna()
    if not len(ik):
        return {"error": "Ninguna barra obtuvo resultado de cortocircuito."}

    ordenadas = ik.sort_values(ascending=False)

    def _fila(idx):
        # Nombre de subestación: primero el mapa del Excel (red CR), que
        # trae el nombre real; si no, el campo name de la red.
        nombre = nombres.get(int(idx))
        if not nombre and "name" in net.bus.columns:
            crudo = net.bus.at[idx, "name"]
            if crudo is not None and not (isinstance(crudo, float) and math.isnan(crudo)):
                nombre = str(crudo).strip().strip("'").strip()
        fila = {
            "bus_index": int(idx),
            "nombre": nombre,
            "vn_kv": _safe_float(net.bus.at[idx, "vn_kv"]),
            "ikss_ka": _safe_float(net.res_bus_sc.at[idx, "ikss_ka"]),
        }
        if "skss_mw" in net.res_bus_sc.columns:
            fila["skss_mva"] = _safe_float(net.res_bus_sc.at[idx, "skss_mw"])
        return fila

    resultado = {
        "network": red,
        "norma": "IEC 60909",
        "tipo_falla": fault_type,
        "caso": case,
        "fuente_datos": fuente,
        "datos_de_maquina_del_modelo": datos_del_modelo,
        "n_buses": int(len(net.bus)),
        "n_buses_with_result": int(len(ik)),
        "ikss_max_ka": _safe_float(ordenadas.iloc[0]),
        "bus_ikss_max": int(ordenadas.index[0]),
        "ikss_min_ka": _safe_float(ordenadas.iloc[-1]),
        "bus_ikss_min": int(ordenadas.index[-1]),
        "ikss_median_ka": _safe_float(ik.median()),
        "limit_applied": limit,
        "buses_mayor_corriente": [_fila(i) for i in ordenadas.index[:limit]],
        "supuestos": supuestos,
    }

    if correccion:
        resultado["correccion_de_datos_aplicada"] = correccion

    avisos = []

    if not datos_del_modelo:
        avisos.append(
            "Resultado calculado con parámetros típicos de literatura, NO "
            "con datos del modelo. Las corrientes son indicativas y no "
            "deben presentarse como características de esta red."
        )

    # Guarda de plausibilidad física. Varias redes de prueba traen
    # tensiones nominales que son marcadores de posición heredados de la
    # conversión de formato (IEEE 14 declara barras en 0.208 kV). Con esas
    # tensiones, cualquier potencia de falla produce corrientes absurdas.
    icc_max = resultado["ikss_max_ka"]
    if icc_max is not None and icc_max > ICC_IMPLAUSIBLE_KA:
        vn_min = _safe_float(net.bus.loc[ik.index, "vn_kv"].min())
        avisos.append(
            "La corriente máxima calculada ({:.0f} kA) excede cualquier "
            "valor físicamente razonable en una red de potencia. La causa "
            "más probable es que las tensiones nominales del modelo sean "
            "marcadores de posición y no datos reales (la mínima con "
            "resultado es {} kV). NO presente estas cifras como "
            "características de la red: informe al usuario que el modelo "
            "no admite un cálculo de cortocircuito válido.".format(
                icc_max, vn_min
            )
        )
        resultado["resultado_implausible"] = True

    if avisos:
        resultado["warning"] = " | ".join(avisos)

    return resultado


# ---------------------------------------------------------------------------
# 5. disconnect_line
# ---------------------------------------------------------------------------

def disconnect_line(line_index):
    """Pone in_service=False en la línea indicada (0-indexed)."""
    net, err = _net_or_error()
    if err:
        return err

    if line_index not in net.line.index:
        return {"error": "Índice de línea {} no existe en la red.".format(line_index)}

    if not net.line.at[line_index, "in_service"]:
        return {
            "line_index": int(line_index),
            "status": "already_disconnected",
        }

    net.line.at[line_index, "in_service"] = False
    return {
        "line_index": int(line_index),
        "from_bus": int(net.line.at[line_index, "from_bus"]),
        "to_bus": int(net.line.at[line_index, "to_bus"]),
        "status": "disconnected",
        "note": "Llame run_power_flow para recalcular el estado de la red.",
    }


# ---------------------------------------------------------------------------
# 6. reconnect_line
# ---------------------------------------------------------------------------

def reconnect_line(line_index):
    """Pone in_service=True en la línea indicada."""
    net, err = _net_or_error()
    if err:
        return err

    if line_index not in net.line.index:
        return {"error": "Índice de línea {} no existe en la red.".format(line_index)}

    if net.line.at[line_index, "in_service"]:
        return {
            "line_index": int(line_index),
            "status": "already_connected",
        }

    net.line.at[line_index, "in_service"] = True
    return {
        "line_index": int(line_index),
        "from_bus": int(net.line.at[line_index, "from_bus"]),
        "to_bus": int(net.line.at[line_index, "to_bus"]),
        "status": "reconnected",
        "note": "Llame run_power_flow para recalcular el estado de la red.",
    }


# ---------------------------------------------------------------------------
# 7. modify_load
# ---------------------------------------------------------------------------

def modify_load(load_index=None, bus_index=None, new_p_mw=None, new_q_mvar=None,
                scale_factor=None):
    """
    Modifica P y/o Q de una carga existente.

    La carga se identifica por `bus_index` (la barra donde está conectada,
    forma preferida) o por `load_index` (índice de la tabla net.load). Si
    se dan ambos deben corresponder a la misma carga. El cambio se expresa
    con `scale_factor` (1.5 = +50 %, aplicado a P y a Q) o con los valores
    finales `new_p_mw` y/o `new_q_mvar`; no se aceptan las dos formas a la
    vez. La aritmética la hace esta función, no el modelo de lenguaje.
    """
    net, err = _net_or_error()
    if err:
        return err

    # --- Resolver qué carga se modifica ---
    if load_index is None and bus_index is None:
        return {"error": "Indique bus_index (barra de la carga) o load_index."}

    if bus_index is not None:
        try:
            bus_index = int(bus_index)
        except (TypeError, ValueError):
            return {"error": "bus_index debe ser un entero."}
        if bus_index not in net.bus.index:
            return {"error": "La barra {} no existe en la red.".format(bus_index)}
        en_barra = list(net.load.index[net.load["bus"] == bus_index])
        if not en_barra:
            con_carga = sorted(int(b) for b in net.load["bus"].unique())
            msg = "La barra {} no tiene cargas conectadas.".format(bus_index)
            if len(con_carga) <= 40:
                msg += " Barras con carga: {}.".format(con_carga)
            else:
                msg += " La red tiene {} cargas en {} barras.".format(
                    len(net.load), len(con_carga))
            return {"error": msg}
        if len(en_barra) > 1 and load_index is None:
            return {
                "error": (
                    "La barra {} tiene {} cargas; indique load_index para "
                    "elegir una.".format(bus_index, len(en_barra))
                ),
                "cargas_en_barra": [
                    {"load_index": int(i),
                     "p_mw": _safe_float(net.load.at[i, "p_mw"]),
                     "q_mvar": _safe_float(net.load.at[i, "q_mvar"])}
                    for i in en_barra
                ],
            }
        if load_index is None:
            load_index = en_barra[0]
        elif int(load_index) not in en_barra:
            return {
                "error": (
                    "La carga {} no está en la barra {} (está en la barra {}). "
                    "Corrija la llamada.".format(
                        load_index, bus_index,
                        int(net.load.at[int(load_index), "bus"])
                        if int(load_index) in net.load.index else "desconocida")
                )
            }

    load_index = int(load_index)
    if load_index not in net.load.index:
        return {"error": "Índice de carga {} no existe en la red.".format(load_index)}

    # --- Resolver el cambio ---
    p_ant = _safe_float(net.load.at[load_index, "p_mw"])
    q_ant = _safe_float(net.load.at[load_index, "q_mvar"])

    if scale_factor is not None and (new_p_mw is not None or new_q_mvar is not None):
        return {"error": "Use scale_factor o valores finales (new_p_mw, new_q_mvar), no ambos."}

    if scale_factor is not None:
        try:
            f = float(scale_factor)
        except (TypeError, ValueError):
            return {"error": "scale_factor debe ser numérico (1.5 = +50 %)."}
        if f < 0:
            return {"error": "scale_factor no puede ser negativo."}
        p_new, q_new = round((p_ant or 0.0) * f, 6), round((q_ant or 0.0) * f, 6)
    elif new_p_mw is not None or new_q_mvar is not None:
        p_new = float(new_p_mw) if new_p_mw is not None else p_ant
        q_new = float(new_q_mvar) if new_q_mvar is not None else q_ant
    else:
        return {"error": "No se especificó ningún cambio (scale_factor, new_p_mw o new_q_mvar)."}

    net.load.at[load_index, "p_mw"] = p_new
    net.load.at[load_index, "q_mvar"] = q_new

    resultado = {
        "load_index": load_index,
        "bus": int(net.load.at[load_index, "bus"]),
        "p_mw_anterior": p_ant,
        "p_mw_nuevo": _safe_float(p_new),
        "q_mvar_anterior": q_ant,
        "q_mvar_nuevo": _safe_float(q_new),
        "status": "modified",
        "note": "Llame run_power_flow para recalcular el estado de la red.",
    }
    if scale_factor is not None:
        resultado["scale_factor"] = f
    return resultado


# ---------------------------------------------------------------------------
# 8. list_available_networks
# ---------------------------------------------------------------------------

def list_available_networks():
    """
    Devuelve el catálogo completo de redes disponibles con nombre y
    descripción. Útil para que el agente descubra dinámicamente qué redes
    puede analizar sin depender de una lista hardcodeada.
    """
    catalogo = []
    for name, info in AVAILABLE_NETWORKS.items():
        catalogo.append({
            "name": name,
            "descripcion": info["descripcion"],
        })
    return {
        "total": len(catalogo),
        "networks": catalogo,
        "note": "Use el campo 'name' como parámetro 'network' en run_power_flow.",
    }


# ---------------------------------------------------------------------------
# 9. reset_network
# ---------------------------------------------------------------------------

def reset_network():
    """
    Limpia el estado interno: descarga la red actual y fuerza recarga
    en la próxima llamada a run_power_flow. También vacía el cache
    de redes CR para que no queden redes mutadas en memoria.
    Útil para el comando /reset de la CLI interactiva.
    """
    _STATE["net"] = None
    _STATE["current_network_name"] = None
    _STATE["endtemp_asumida"] = False
    _limpiar_cache_cr()
    return {"status": "reset", "note": "Red descargada. Llame run_power_flow para cargar una nueva."}


# ---------------------------------------------------------------------------
# Dispatcher único
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "run_power_flow": run_power_flow,
    "get_voltage_violations": get_voltage_violations,
    "get_overloaded_lines": get_overloaded_lines,
    "run_short_circuit": run_short_circuit,
    "disconnect_line": disconnect_line,
    "reconnect_line": reconnect_line,
    "modify_load": modify_load,
    "list_available_networks": list_available_networks,
}


def execute_tool(tool_name, tool_input):
    """
    Ejecuta una herramienta por nombre. Si el nombre no está registrado,
    devuelve un error en vez de lanzar excepción (para que el LLM pueda
    reintentar con un nombre válido).
    """
    if tool_name not in TOOL_FUNCTIONS:
        return {
            "error": "Tool desconocida: {!r}. Disponibles: {}".format(
                tool_name, list(TOOL_FUNCTIONS)
            )
        }
    try:
        return TOOL_FUNCTIONS[tool_name](**(tool_input or {}))
    except TypeError as e:
        return {"error": "Argumentos inválidos para {}: {}".format(tool_name, e)}
    except Exception as e:
        return {"error": "Excepción en {}: {}".format(tool_name, e)}
    
