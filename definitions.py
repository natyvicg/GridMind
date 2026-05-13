"""
definitions.py — Esquemas JSON Schema de las herramientas para Anthropic y OpenAI.

Arquitectura:
    BASE_DEFS es la fuente de verdad única. Cada herramienta se define una
    sola vez con {name, description, input_schema}. Las funciones
    build_anthropic_tools() y build_openai_tools() adaptan al formato que
    cada API espera, sin duplicar definiciones.

    Para agregar una herramienta nueva: añadirla a BASE_DEFS y las dos
    listas exportadas (ANTHROPIC_TOOLS, OPENAI_TOOLS) se actualizan
    automáticamente.

Notas sobre los schemas:
    - Las descripciones de v_min/v_max en get_voltage_violations distinguen
      explícitamente entre "umbral operacional" y "valor observado", y
      recomiendan OMITIR el parámetro para usar el default estándar.
    - La propiedad `default` (JSON Schema Draft-07) refuerza la lectura del
      schema aunque la API del LLM no la aplique automáticamente.
    - El parámetro `limit` acota resultados en redes grandes (CR, 524 barras).
"""

# ---------------------------------------------------------------------------
# Definición base — neutral respecto al proveedor
# ---------------------------------------------------------------------------

BASE_DEFS = [
    {
        "name": "run_power_flow",
        "description": (
            "Carga (si hace falta) la red eléctrica indicada y corre el flujo "
            "de potencia con el método Newton-Raphson. Devuelve un resumen "
            "global: convergencia, número de barras, Vmin/Vmax (pu), y carga "
            "máxima de líneas y transformadores. Esta herramienta DEBE "
            "invocarse antes de get_voltage_violations o get_overloaded_lines, "
            "y de nuevo cada vez que la red sea modificada (disconnect_line, "
            "reconnect_line, modify_load) para que los resultados reflejen el "
            "estado actualizado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "network": {
                    "type": "string",
                    "description": (
                        "Nombre de la red a cargar (ej. 'IEEE_14', 'IEEE_118', "
                        "'CR_Min'). Llame list_available_networks para ver "
                        "todas las opciones disponibles. Si se omite, se "
                        "conserva la red previamente cargada."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_voltage_violations",
        "description": (
            "Devuelve las barras cuya tensión viola los límites OPERACIONALES "
            "estándar [v_min=0.95, v_max=1.05] pu, ordenadas de la más severa "
            "a la menos severa. Requiere haber ejecutado run_power_flow "
            "previamente. RECOMENDACIÓN: en la mayoría de los casos, OMITA "
            "los parámetros v_min y v_max para usar los defaults estándar; "
            "modifíquelos sólo si el usuario solicita umbrales específicos. "
            "Para redes grandes (CR), use el parámetro `limit` para acotar "
            "el número de filas devueltas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "v_min": {
                    "type": "number",
                    "default": 0.95,
                    "description": (
                        "UMBRAL inferior de tensión en pu (estándar operacional, "
                        "no valor observado). Default 0.95. NO copie aquí el "
                        "Vmin observado en run_power_flow: este parámetro es "
                        "el umbral CONTRA el que se compara, no el dato medido. "
                        "Omita este parámetro salvo que el usuario pida un "
                        "umbral específico distinto a 0.95."
                    ),
                },
                "v_max": {
                    "type": "number",
                    "default": 1.05,
                    "description": (
                        "UMBRAL superior de tensión en pu (estándar operacional, "
                        "no valor observado). Default 1.05. NO copie aquí el "
                        "Vmax observado en run_power_flow: este parámetro es "
                        "el umbral CONTRA el que se compara, no el dato medido. "
                        "Omita este parámetro salvo que el usuario pida un "
                        "umbral específico distinto a 1.05."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": (
                        "Número máximo de violaciones a devolver (las más "
                        "severas). Default 20. En redes pequeñas (IEEE 14) el "
                        "default es suficiente; en redes grandes (CR), use un "
                        "valor explícito acorde a lo que solicite el usuario."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_overloaded_lines",
        "description": (
            "Devuelve las líneas con carga superior al umbral indicado, "
            "ordenadas de mayor a menor. Requiere haber ejecutado "
            "run_power_flow previamente. Use `limit` para acotar el número "
            "de filas en redes grandes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "loading_threshold": {
                    "type": "number",
                    "default": 100.0,
                    "description": (
                        "Umbral de carga en %. Default 100 (línea sobrecargada). "
                        "Omita este parámetro salvo que el usuario pida otro umbral."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": (
                        "Número máximo de líneas a devolver. Default 20."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "disconnect_line",
        "description": (
            "Desconecta (in_service=False) la línea indicada por su índice "
            "0-indexed. Después de llamar esta tool, vuelva a invocar "
            "run_power_flow para recalcular el estado de la red."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "line_index": {
                    "type": "integer",
                    "description": (
                        "Índice 0-indexed de la línea en net.line. Para "
                        "IEEE 14 con convención IEEE 1-indexed (L1-2, L2-5, "
                        "etc.), reste 1 antes de pasar el índice."
                    ),
                }
            },
            "required": ["line_index"],
        },
    },
    {
        "name": "reconnect_line",
        "description": (
            "Reconecta (in_service=True) una línea previamente desconectada. "
            "Después de llamar esta tool, vuelva a invocar run_power_flow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "line_index": {
                    "type": "integer",
                    "description": "Índice 0-indexed de la línea.",
                }
            },
            "required": ["line_index"],
        },
    },
    {
        "name": "modify_load",
        "description": (
            "Modifica la potencia activa (P) y/o reactiva (Q) de una carga "
            "existente. Después de llamar esta tool, vuelva a invocar "
            "run_power_flow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "load_index": {
                    "type": "integer",
                    "description": "Índice 0-indexed de la carga en net.load.",
                },
                "new_p_mw": {
                    "type": "number",
                    "description": "Nueva potencia activa en MW. Opcional.",
                },
                "new_q_mvar": {
                    "type": "number",
                    "description": "Nueva potencia reactiva en MVAr. Opcional.",
                },
            },
            "required": ["load_index"],
        },
    },
    {
        "name": "list_available_networks",
        "description": (
            "Devuelve el catálogo completo de redes disponibles con nombre "
            "y descripción. Llame esta herramienta cuando el usuario pregunte "
            "qué redes hay disponibles, o cuando necesite verificar el nombre "
            "exacto de una red antes de pasarlo a run_power_flow. No requiere "
            "parámetros."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Conversión a formato Anthropic
# ---------------------------------------------------------------------------

def build_anthropic_tools():
    """Anthropic acepta directamente {name, description, input_schema}."""
    return [dict(d) for d in BASE_DEFS]


# ---------------------------------------------------------------------------
# Conversión a formato OpenAI
# ---------------------------------------------------------------------------

def build_openai_tools():
    """OpenAI usa {type:'function', function:{name, description, parameters}}."""
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": d["input_schema"],
            },
        }
        for d in BASE_DEFS
    ]


ANTHROPIC_TOOLS = build_anthropic_tools()
OPENAI_TOOLS = build_openai_tools()
