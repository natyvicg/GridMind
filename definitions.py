"""
definitions.py — Esquemas JSON Schema de las herramientas para la API de Anthropic.

Arquitectura:
    BASE_DEFS es la fuente de verdad única. Cada herramienta se define una
    sola vez con {name, description, input_schema}. La función
    build_anthropic_tools() adapta al formato que la API espera.

    Para agregar una herramienta nueva: añadirla a BASE_DEFS y la lista
    exportada (ANTHROPIC_TOOLS) se actualiza automáticamente.

Notas sobre los schemas:
    - Las descripciones de v_min/v_max en get_voltage_violations distinguen
      explícitamente entre "umbral operacional" y "valor observado", y
      recomiendan OMITIR el parámetro para usar el default estándar.
    - La propiedad `default` (JSON Schema Draft-07) refuerza la lectura del
      schema aunque la API del LLM no la aplique automáticamente.
    - El parámetro `limit` acota resultados en redes grandes (CR, 524 barras).
    - La descripción de run_short_circuit advierte que las redes IEEE no
      traen datos de cortocircuito, para que el modelo interprete el error
      como comportamiento esperado y no reintente con valores inventados.
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
            "estándar [v_min=0.95, v_max=1.05] pu. La lista `violations` viene "
            "ordenada por DESVIACION ABSOLUTA respecto al umbral violado, de "
            "mayor a menor, mezclando subtensiones y sobretensiones: use ese "
            "orden cuando el usuario pida las mas severas. Devuelve tambien "
            "top5_subtension y top5_sobretension, que son las 5 peores de cada "
            "tipo y NUNCA se recortan por `limit`, y los conteos completos "
            "n_subtension y n_sobretension. Requiere haber ejecutado "
            "run_power_flow previamente. RECOMENDACION: en la mayoria de los "
            "casos, OMITA los parametros v_min y v_max para usar los defaults "
            "estandar; modifiquelos solo si el usuario solicita umbrales "
            "especificos. Para redes grandes (CR), use `limit` para acotar el "
            "numero de filas."
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
            "Devuelve los elementos serie con cargabilidad superior al umbral "
            "indicado, ordenados de mayor a menor. Cubre LÍNEAS Y "
            "TRANSFORMADORES, con conteos separados: n_overloaded_total son "
            "las líneas, n_overloaded_trafos los transformadores, y "
            "n_overloaded_elementos la suma. IMPORTANTE: la red de Costa Rica "
            "tiene 137 líneas y 256 transformadores, así que una contingencia "
            "puede sobrecargar transformadores sin sobrecargar ninguna línea. "
            "Nunca concluya que la red está sin sobrecargas mirando solo las "
            "líneas: revise siempre los dos conteos. Requiere haber ejecutado "
            "run_power_flow previamente. Use `limit` para acotar el número de "
            "filas en redes grandes."
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
        "name": "run_short_circuit",
        "description": (
            "Calcula la corriente de cortocircuito segun la norma IEC 60909 "
            "sobre la red cargada. Devuelve la corriente inicial simetrica "
            "de cortocircuito Ik'' en kA: maxima, minima, mediana y las "
            "barras de mayor corriente. Requiere haber ejecutado "
            "run_power_flow previamente. "
            "PROCEDENCIA DE DATOS (IMPORTANTE): el calculo necesita la "
            "impedancia de las fuentes, que el flujo de carga no usa. Solo "
            "las redes de Costa Rica (CR_Min, CR_Med, CR_Max) la traen en su "
            "modelo de origen. Las redes de prueba IEEE NO la traen, porque "
            "se publicaron como casos de flujo de carga; con ellas esta "
            "herramienta devuelve un error que nombra los parametros "
            "faltantes, y ese es el comportamiento correcto y esperado: "
            "reportelo al usuario tal cual, no lo trate como una falla ni "
            "reintente con otros argumentos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fault_type": {
                    "type": "string",
                    "enum": ["3ph", "2ph"],
                    "default": "3ph",
                    "description": (
                        "Tipo de falla. '3ph' es la falla trifasica, caso "
                        "base de IEC 60909 y el valor por defecto. '2ph' es "
                        "bifasica. Omita este parametro salvo pedido "
                        "explicito del usuario."
                    ),
                },
                "case": {
                    "type": "string",
                    "enum": ["max", "min"],
                    "default": "max",
                    "description": (
                        "Condicion de calculo. 'max' entrega la corriente "
                        "maxima de cortocircuito, que es la que se usa para "
                        "dimensionar equipo, y es el valor por defecto. "
                        "'min' entrega la minima, usada para verificar "
                        "sensibilidad de protecciones."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": (
                        "Numero maximo de barras a listar, ordenadas de mayor "
                        "a menor corriente. Default 20. En la red CR (524 "
                        "barras) use un valor acorde a lo que pida el usuario."
                    ),
                },
                "s_sc_interconexion_mva": {
                    "type": "number",
                    "description": (
                        "Solo para las redes CR. Potencia de cortocircuito "
                        "equivalente, en MVA, de las interconexiones con "
                        "Nicaragua y Panama, que el modelo de origen no "
                        "especifica. OMITA este parametro para usar el valor "
                        "declarado por defecto (2000 MVA). Pase un valor solo "
                        "si el usuario pide evaluar la sensibilidad a este "
                        "supuesto."
                    ),
                },
                "parametros_tipicos": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "NO active este parametro por iniciativa propia. "
                        "Solo en true si el usuario pide explicitamente un "
                        "calculo indicativo con parametros tipicos de "
                        "literatura sobre una red que no tiene datos de "
                        "cortocircuito. El resultado se rotula como basado "
                        "en supuestos y trae un warning que debe transmitir "
                        "al usuario."
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


ANTHROPIC_TOOLS = build_anthropic_tools()
