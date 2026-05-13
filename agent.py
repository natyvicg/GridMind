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
MAX_TOKENS_PER_CALL = 1500


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

PROTOCOLO DE TRABAJO
1. Antes de responder con datos numéricos, ejecute run_power_flow al menos una vez. Si la red ya \
está cargada, la herramienta es barata; no la salte.
2. Tras cualquier modificación (disconnect_line, reconnect_line, modify_load), VUELVA A LLAMAR \
run_power_flow antes de leer violaciones o sobrecargas.
3. En la respuesta final al usuario, presente cifras con precisión razonable (4 decimales para pu, \
2 para %), e indique las unidades.
4. Si una herramienta devuelve un campo "error", repórtelo al usuario con honestidad — no \
fabrique resultados.
5. Si una herramienta devuelve un campo "warning", LEALO con atención: probablemente indica \
que un parámetro fue mal elegido. Reconsidere la llamada y vuelva a invocar la herramienta con \
los argumentos corregidos antes de responder al usuario.
"""


# ---------------------------------------------------------------------------
# Loop ReAct
# ---------------------------------------------------------------------------

def run_react_loop(user_query, client=None, system=SYSTEM_PROMPT, verbose=False):
    """
    Ejecuta el loop ReAct para una consulta. Devuelve un dict con:
      - final_text: respuesta final del agente (str)
      - messages: lista completa de mensajes intercambiados
      - tool_calls: lista de {name, input, result} en orden de invocación
      - usage: {input_tokens, output_tokens} agregado de todas las llamadas
      - iterations: número de iteraciones realizadas
      - stop_reason: razón de parada de la última llamada
    """
    if client is None:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    messages = [{"role": "user", "content": user_query}]
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
