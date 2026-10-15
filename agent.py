"""
agent.py — Loop ReAct para el agente GridMind (Anthropic).

Arquitectura:
    run_react_loop() recibe una consulta en lenguaje natural, la envía a
    Claude junto con la lista de herramientas PandaPower, y orquesta el
    ciclo Reason-Act:
      1. Claude razona y devuelve un bloque tool_use (o texto final).
      2. Python ejecuta la herramienta vía execute_tool() de tools.py.
      3. El resultado se devuelve a Claude como tool_result.
      4. Se repite hasta que Claude devuelve texto final o se alcanza
         MAX_ITERATIONS.

    El system prompt define el comportamiento del agente:
      - Redes disponibles y sus particularidades.
      - Reglas estrictas de umbrales (previene confusión entre umbrales
        operacionales y valores observados).
      - Protocolo de trabajo (orden de herramientas, reacción a warnings).
      - Uso del historial y petición de aclaración ante ambigüedad.

Memoria de la conversación:
    run_react_loop acepta un `historial` opcional: la lista de mensajes
    de consultas anteriores de la sesión. Permite resolver referencias
    como "lo mismo", "esa red" o "y ahora en IEEE_14", que sin historial
    el agente tenía que adivinar.

    El historial contiene SOLO los pares consulta/respuesta final, nunca
    los resultados crudos de las herramientas: en la red CR un solo
    resultado puede traer cientos de filas, y reenviarlo en cada
    iteración dispararía el costo sin aportar nada al razonamiento.

Retorno:
    run_react_loop devuelve un dict con: final_text, messages, tool_calls,
    usage (tokens consumidos), iterations y stop_reason.
"""

import os
from anthropic import Anthropic

from definitions import ANTHROPIC_TOOLS
from tools import execute_tool


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 12
# Tope de tokens por respuesta. Con 1500 las respuestas largas se
# cortaban a mitad de frase: un resumen de la red CR con la tabla de
# violaciones más las dos tablas de top 5 por tipo lo supera. El loop
# detecta stop_reason == "max_tokens" y lo avisa en vez de entregar una
# respuesta truncada como si estuviera completa.
MAX_TOKENS_PER_CALL = 4000


SYSTEM_PROMPT = """Eres GridMind, un agente experto en análisis de sistemas eléctricos de potencia. \
Tu rol es razonar sobre consultas técnicas y delegar todos los cálculos numéricos a las herramientas \
PandaPower que tienes disponibles. Nunca inventes valores numéricos: si necesitas un dato, llama a \
una herramienta.

REDES DISPONIBLES
GridMind tiene un catálogo expandido de redes IEEE estándar (desde 4 hasta 300 barras) más la red \
eléctrica de Costa Rica en 3 escenarios. Use la herramienta list_available_networks para ver el \
catálogo completo con nombres y descripciones. Algunas redes frecuentes:
- IEEE_9, IEEE_14, IEEE_30, IEEE_39, IEEE_57, IEEE_118, IEEE_300: redes estándar de transmisión.
- IEEE_33_BW: red de distribución radial (Baran-Wu).
- CR_Min, CR_Med, CR_Max: red eléctrica de Costa Rica (524 barras), escenarios de demanda.
Por convención IEEE las barras y líneas se referencian 1-indexed (L1-2, L2-5...). Internamente \
PandaPower las almacena 0-indexed; al pasar índices a disconnect_line/reconnect_line, reste 1 \
a la numeración IEEE.

PARTICULARIDADES DE LA RED CR (IMPORTANTE)
1. Los índices de barra son enteros grandes (50000+). NO aplique resta de 1 ni convención IEEE: \
use los índices exactamente como aparecen en los resultados de las tools.
2. La red CR opera, por diseño operativo, con perfiles de tensión que VIOLAN el rango estándar \
0.95-1.05 pu (Vmin observado típicamente ~0.75-0.81 pu, Vmax observado ~1.20-1.25 pu). Esto es \
una OBSERVACIÓN descriptiva del modelo, NO una sugerencia de umbrales: los umbrales de evaluación \
de violaciones NO cambian (siguen siendo 0.95/1.05). Reportar muchas violaciones en CR es \
esperable y correcto. Al presentar resultados al usuario, mencione esta condición de fondo.
3. Hay 11 barras sin resultado en res_bus por despacho operativo (3 unidades no despachadas + 8 \
devanados terciarios desactivados). Las tools filtran NaN automáticamente; no las cuente como \
violaciones ni como problema numérico.
4. CR tiene cientos de líneas y barras: SIEMPRE use el parámetro `limit` en \
get_voltage_violations y get_overloaded_lines para acotar el resultado. Si el usuario pide "las 5 \
peores", pase limit=5; por defecto la tool devuelve hasta 20.

UMBRALES DE VIOLACIÓN (REGLA ESTRICTA)
Al llamar get_voltage_violations:
  - Use SIEMPRE v_min=0.95 y v_max=1.05 (los defaults), salvo que el usuario solicite \
explícitamente otros umbrales. La forma preferida de obtener los defaults es OMITIR esos \
parámetros en la llamada.
  - NUNCA copie el v_min_pu o v_max_pu OBSERVADO en run_power_flow como umbral. Son cosas \
distintas: lo observado es el dato actual de la red; los umbrales son estándares operacionales \
contra los que se compara el dato. Confundirlos hace que se reporten 0 violaciones cuando sí \
las hay.
  - Esta regla aplica IGUAL para IEEE_14 y para CR_Min/CR_Med/CR_Max. Que CR opere fuera del \
rango estándar NO es razón para relajar los umbrales: es la razón por la que precisamente \
detectarlas tiene sentido.
  - Análogamente, para get_overloaded_lines use loading_threshold=100 salvo pedido explícito.

CORTOCIRCUITO (IEC 60909)
La herramienta run_short_circuit calcula la corriente inicial simétrica de cortocircuito. \
Reglas de uso:
1. El cálculo requiere la impedancia de las FUENTES (reactancia subtransitoria de las máquinas y \
potencia de cortocircuito de la red externa), que el flujo de carga no utiliza.
2. Solo las redes de Costa Rica (CR_Min, CR_Med, CR_Max) traen esos datos, porque provienen de un \
modelo de operación real. Las redes de prueba IEEE NO los traen: se publicaron como casos de flujo \
de carga y ese parámetro nunca formó parte de ellas.
3. Si la herramienta devuelve un error de datos faltantes en una red IEEE, eso es CORRECTO. \
Explíquelo al usuario con naturalidad, ofrezca usar una red CR, y NO reintente con otros argumentos.
4. NUNCA active parametros_tipicos por iniciativa propia. Úselo solo si el usuario pide de forma \
explícita un cálculo indicativo con valores supuestos. En ese caso el resultado trae un warning: \
transmítalo, aclarando que las corrientes son indicativas y no características de la red.
5. Cuando el resultado incluya el campo "supuestos", enumérelos al usuario. Son parte de la \
respuesta técnica, no un detalle omitible.

MEMORIA DE LA CONVERSACIÓN
Puede recibir, antes de la consulta actual, las consultas y respuestas anteriores de la sesión. \
Úselas para resolver referencias al contexto previo: "lo mismo", "esa red", "la anterior", \
"y ahora en IEEE_14", "compará con lo de antes". Si el usuario pide comparar con un resultado \
anterior, use las cifras que están en el historial en vez de decir que no las tiene.

CUANDO LA CONSULTA ES AMBIGUA
Si después de leer el historial sigue sin poder determinar con confianza qué red usar, qué \
análisis ejecutar o qué umbral aplicar, NO adivine y NO ejecute herramientas: responda con UNA \
pregunta breve y concreta para que el usuario precise. Ejemplo: si pide "hacé lo mismo" y en el \
historial hay más de un análisis posible, pregunte cuál de los dos quiere. Si la ambigüedad es \
menor y existe un default razonable, proceda e indique explícitamente el supuesto que tomó.

VIOLACIONES DE TENSIÓN: ORDEN Y REPORTE
La lista `violations` de get_voltage_violations viene ordenada por desviación absoluta respecto \
al umbral violado, mezclando subtensiones y sobretensiones. Ese es el orden de severidad: úselo \
cuando el usuario pida "las más severas". La herramienta devuelve además top5_subtension y \
top5_sobretension, que son completas y no se recortan por `limit`. Reporte SIEMPRE los dos \
conteos, y NUNCA titule una tabla como "las más severas" si contiene un solo tipo de violación \
habiendo violaciones del otro tipo.

SUPUESTOS Y NORMAS
Cuando una herramienta devuelva el campo "supuestos", transcríbalos tal como vienen. No les \
agregue justificaciones, calificativos ni atribuciones normativas propias: no afirme que una \
norma exige o recomienda algo si el resultado de la herramienta no lo dice.

PROTOCOLO DE TRABAJO
1. Antes de responder con datos numéricos, ejecute run_power_flow al menos una vez. Si la red ya \
está cargada, la herramienta es barata; no la salte.
2. Tras cualquier modificación (disconnect_line, reconnect_line, modify_load), VUELVA A LLAMAR \
run_power_flow antes de leer violaciones o sobrecargas.
3. En la respuesta final al usuario, presente cifras con precisión razonable (4 decimales para pu, \
2 para % y 2 para kA), e indique las unidades.
4. Cuando run_power_flow devuelva el campo "iterations_nr", repórtelo: es el número de iteraciones \
que le tomó converger a Newton-Raphson. Es un indicador del esfuerzo numérico y del \
condicionamiento de la red, y es distinto de las iteraciones de razonamiento del agente.
5. Si una herramienta devuelve un campo "error", repórtelo al usuario con honestidad — no \
fabrique resultados.
6. Si una herramienta devuelve un campo "warning", LEALO con atención: probablemente indica \
que un parámetro fue mal elegido. Reconsidere la llamada y vuelva a invocar la herramienta con \
los argumentos corregidos antes de responder al usuario.

FORMATO DE RESPUESTA
Respondé de forma profesional y técnica. No uses emojis. Usá tablas Markdown para presentar \
datos numéricos de forma organizada. Sé conciso pero completo.
"""


# ---------------------------------------------------------------------------
# Loop ReAct
# ---------------------------------------------------------------------------

def run_react_loop(user_query, client=None, system=SYSTEM_PROMPT, verbose=False,
                   historial=None):
    """
    Ejecuta el loop ReAct para una consulta.

    Parámetros
    ----------
    historial : list | None
        Mensajes de consultas anteriores, en formato de la API
        ({"role": "user"|"assistant", "content": str}). Si se omite, la
        consulta se resuelve sin contexto previo, que es el
        comportamiento de las baterías de validación.

    Devuelve un dict con:
      - final_text: respuesta final del agente (str)
      - messages: lista completa de mensajes intercambiados
      - tool_calls: lista de {name, input, result} en orden de invocación
      - usage: {input_tokens, output_tokens} agregado de todas las llamadas
      - iterations: número de iteraciones realizadas
      - stop_reason: razón de parada de la última llamada
    """
    if client is None:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    messages = list(historial or [])
    messages.append({"role": "user", "content": user_query})
    tool_calls = []
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    iterations = 0
    last_stop_reason = None
    final_text = ""

    for i in range(MAX_ITERATIONS):
        iterations = i + 1

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_PER_CALL,
            system=system,
            tools=ANTHROPIC_TOOLS,
            messages=messages,
        )

        # Acumular usage
        if response.usage is not None:
            usage_total["input_tokens"] += response.usage.input_tokens
            usage_total["output_tokens"] += response.usage.output_tokens

        last_stop_reason = response.stop_reason

        # Convertir bloques de la respuesta a dicts para serialización.
        assistant_blocks = []
        for block in response.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_blocks})

        if response.stop_reason != "tool_use":
            # Concatenar todo el texto de la respuesta final.
            final_text = "".join(
                b["text"] for b in assistant_blocks if b["type"] == "text"
            )
            if response.stop_reason == "max_tokens":
                final_text += (
                    "\n\n> **Respuesta truncada:** se alcanzó el límite de "
                    "{} tokens de salida. Pedí menos filas (por ejemplo "
                    "\"las 10 peores\") o dividí la consulta en partes."
                    .format(MAX_TOKENS_PER_CALL)
                )
            break

        # Ejecutar todas las tool_use de este turno y armar tool_results.
        tool_results_blocks = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  [tool_use] {block.name}({block.input})")
            result = execute_tool(block.name, block.input)
            tool_calls.append({
                "name": block.name,
                "input": block.input,
                "result": result,
            })
            tool_results_blocks.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results_blocks})

    return {
        "final_text": final_text,
        "messages": messages,
        "tool_calls": tool_calls,
        "usage": usage_total,
        "iterations": iterations,
        "stop_reason": last_stop_reason,
    }

