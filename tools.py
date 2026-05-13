"""
tools.py — Herramientas PandaPower que GridMind expone al LLM.

Funciones disponibles:
    run_power_flow          Carga red y ejecuta flujo de potencia Newton-Raphson.
    get_voltage_violations  Detecta barras con tensión fuera de rango operacional.
    get_overloaded_lines    Detecta líneas con cargabilidad excesiva.
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
"""

import math
import pandapower as pp
import pandapower.networks as pn

from red_cr_loader import cargar_red_cr


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
    Devuelve las barras cuya tensión está fuera de [v_min, v_max]. Resultado
    ordenado por severidad (las más bajas primero, luego las más altas).
    El parámetro `limit` recorta a las N más severas para evitar inflar el
    contexto del LLM con redes grandes.

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

    def _fila(idx, val, tipo):
        return {
            "bus_index": int(idx) if isinstance(idx, (int, float)) else idx,
            "vm_pu": _safe_float(val),
            "tipo": tipo,
        }

    violaciones = (
        [_fila(i, v, "subtension") for i, v in bajas.items()]
        + [_fila(i, v, "sobretension") for i, v in altas.items()]
    )

    resultado = {
        "network": _STATE["current_network_name"],
        "v_min_threshold": v_min,
        "v_max_threshold": v_max,
        "n_violations_total": len(violaciones),
        "n_subtension": int(len(bajas)),
        "n_sobretension": int(len(altas)),
        "limit_applied": limit,
        "violations": violaciones[:limit],
    }
    if warnings:
        resultado["warning"] = " | ".join(warnings)
    return resultado


# ---------------------------------------------------------------------------
# 3. get_overloaded_lines
# ---------------------------------------------------------------------------

def get_overloaded_lines(loading_threshold=100.0, limit=20):
    """
    Devuelve las líneas cuya carga supera el umbral (en %), ordenadas de
    mayor a menor carga. `limit` recorta para no inflar contexto.
    """
    net, err = _net_or_error()
    if err:
        return err

    if net.res_line.empty:
        return {"error": "No hay resultados de líneas. Llame run_power_flow primero."}

    loading = net.res_line["loading_percent"].dropna()
    sobrecargadas = loading[loading > loading_threshold].sort_values(ascending=False)

    filas = []
    for line_idx, lp in sobrecargadas.items():
        from_bus = net.line.at[line_idx, "from_bus"]
        to_bus = net.line.at[line_idx, "to_bus"]
        filas.append({
            "line_index": int(line_idx),
            "from_bus": int(from_bus) if not math.isnan(float(from_bus)) else None,
            "to_bus": int(to_bus) if not math.isnan(float(to_bus)) else None,
            "loading_percent": _safe_float(lp),
        })

    return {
        "network": _STATE["current_network_name"],
        "loading_threshold_percent": loading_threshold,
        "n_overloaded_total": len(filas),
        "limit_applied": limit,
        "overloaded_lines": filas[:limit],
    }


# ---------------------------------------------------------------------------
# 4. disconnect_line
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
# 5. reconnect_line
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
# 6. modify_load
# ---------------------------------------------------------------------------

def modify_load(load_index, new_p_mw=None, new_q_mvar=None):
    """Modifica P y/o Q de una carga existente."""
    net, err = _net_or_error()
    if err:
        return err

    if load_index not in net.load.index:
        return {"error": "Índice de carga {} no existe en la red.".format(load_index)}

    cambios = {}
    if new_p_mw is not None:
        cambios["p_mw_anterior"] = _safe_float(net.load.at[load_index, "p_mw"])
        net.load.at[load_index, "p_mw"] = float(new_p_mw)
        cambios["p_mw_nuevo"] = float(new_p_mw)

    if new_q_mvar is not None:
        cambios["q_mvar_anterior"] = _safe_float(net.load.at[load_index, "q_mvar"])
        net.load.at[load_index, "q_mvar"] = float(new_q_mvar)
        cambios["q_mvar_nuevo"] = float(new_q_mvar)

    if not cambios:
        return {"error": "No se especificó ningún cambio (new_p_mw o new_q_mvar)."}

    cambios["load_index"] = int(load_index)
    cambios["bus"] = int(net.load.at[load_index, "bus"])
    cambios["status"] = "modified"
    cambios["note"] = "Llame run_power_flow para recalcular el estado de la red."
    return cambios


# ---------------------------------------------------------------------------
# 7. list_available_networks
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
# 8. reset_network
# ---------------------------------------------------------------------------

def reset_network():
    """
    Limpia el estado interno: descarga la red actual y fuerza recarga
    en la próxima llamada a run_power_flow. Útil para el comando /reset
    de la CLI interactiva.
    """
    _STATE["net"] = None
    _STATE["current_network_name"] = None
    return {"status": "reset", "note": "Red descargada. Llame run_power_flow para cargar una nueva."}


# ---------------------------------------------------------------------------
# Dispatcher único
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "run_power_flow": run_power_flow,
    "get_voltage_violations": get_voltage_violations,
    "get_overloaded_lines": get_overloaded_lines,
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
