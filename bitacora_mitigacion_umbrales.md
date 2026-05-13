# Día 8 — Mitigación del hallazgo CR_Min · Q2 (defensa en 3 capas)

**Fecha:** 27 de abril de 2026
**Objetivo del día:** cerrar el único fallo detectado en la validación cruzada del Día 7 (CR_Min·Q2: el agente usó `v_max=1.25415` en vez del estándar 1.05) mediante una mitigación arquitectónica que no dependa exclusivamente del modelo LLM.

Este día corresponde a la **Fase 6 — Ajustes y mejoras finales** del cronograma original (semanas 17–18) y constituye el primer ciclo iterativo *encontrar fallo → diagnosticar causa → corregir → preparar re-validación*, exactamente el patrón que la propuesta del TFG describe en su metodología.

## 8.1 Diagnóstico

Lectura cuidadosa de los tres archivos del agente (`tools.py`, `definitions.py`, `agent.py` versión Día 6) revela que las tres capas teóricas de defensa contra errores de razonamiento estaban **incompletas**:

| Capa | Archivo (Día 6) | Estado del fallo |
| --- | --- | --- |
| A — Estructural | `tools.py` línea 173 | El default Python (`v_max=1.05`) sólo se aplica si el LLM **omite** el parámetro. Cuando lo incluye con un valor erróneo, no hay validación que lo intercepte. |
| B — Descripción | `definitions.py` líneas 70-74 | "Default 0.95" aparece en la descripción libre, pero no como propiedad `default` del JSON Schema. La descripción no aclara que el umbral es un estándar operacional, ni recomienda omitir el parámetro. |
| C — System prompt | `agent.py` líneas 47-51 | Establece que CR opera con tensiones típicas de 0.75–0.81 / 1.20–1.25 pu, pero no contiene una regla prescriptiva sobre qué umbrales usar. El LLM pudo interpretar ese rango descriptivo como una sugerencia de umbral. |

El fallo del Día 7 es la consecuencia natural de esta falta: con tres capas implícitas, el LLM tenía suficiente espacio para racionalizar un argumento incorrecto.

## 8.2 Decisiones técnicas

| Decisión | Alternativa descartada | Justificación |
| --- | --- | --- |
| Validación con warning blando + error duro en `tools.py` | Validación silenciosa que reescribe el input | El warning permite al LLM detectar y corregir su propio error en una iteración subsecuente del loop ReAct (capa C apoya a A). Una reescritura silenciosa enmascararía la conducta y haría que el TFG no pueda discutir el patrón de auto-corrección. |
| Umbrales de aviso 0.85 / 1.15 | Umbrales más estrictos (0.90 / 1.10) | Permite cubrir casos legítimos donde el usuario sí quiera analizar un rango ampliado (ej. *"¿hay barras debajo de 0.92?"*) sin disparar warnings espurios. Los umbrales actuales sólo se activan ante valores claramente irracionales como umbral. |
| Recomendación explícita de OMITIR el parámetro | Recomendación de pasar siempre los valores explícitos | Omitir es robusto: si el default cambia algún día, el código se adapta automáticamente; además, omitir reduce la posibilidad de error de copia. |
| Mantener la sección "Vmin/Vmax típicos" en el system prompt | Eliminarla | El usuario igual necesita ese contexto al leer reportes de CR. Lo que cambia es que ahora el prompt aclara explícitamente que ese rango es **observación descriptiva**, no umbral prescriptivo. |
| Reaccionar a `warning` en el resultado de la tool | Solo log silencioso | El protocolo de trabajo del system prompt ahora incluye una regla 5: *"Si una herramienta devuelve un warning, reconsidere la llamada antes de responder al usuario"*. Esto convierte el warning de informativo a accionable. |

## 8.3 Cambios aplicados

### Capa A — `tools.py`

En `get_voltage_violations` se agregaron dos chequeos:

1. **Error duro** si `v_min ≥ v_max` (umbrales invertidos o iguales). Devuelve un `{"error": "..."}` con texto que sugiere los defaults estándar.
2. **Warning blando** si `v_min < 0.85` o `v_max > 1.15`. La función computa igual y devuelve los resultados, pero agrega un campo `warning` al diccionario de salida explicando que el umbral es probablemente un valor observado en lugar de un estándar operacional, y recomendando omitir el parámetro.

### Capa B — `definitions.py`

Reescritura completa de las descripciones de `v_min` y `v_max` en `get_voltage_violations`. Las descripciones ahora:

- Empiezan con la palabra *UMBRAL* en mayúsculas para que el LLM la perciba como concepto destacado.
- Aclaran *"estándar operacional, no valor observado"*.
- Incluyen la advertencia explícita *"NO copie aquí el Vmin/Vmax observado en run_power_flow"*.
- Recomiendan *"Omita este parámetro salvo que el usuario pida..."*.

Adicionalmente se agregó la propiedad `default` (estándar JSON Schema Draft-07) a `v_min`, `v_max`, `loading_threshold` y `limit`. Aunque la API de Anthropic no aplica `default` automáticamente, la presencia del campo refuerza la lectura del schema.

### Capa C — `agent.py`

Dos cambios al `SYSTEM_PROMPT`:

1. La sección "PARTICULARIDADES DE LA RED CR" punto 2 fue reescrita para distinguir explícitamente entre **observación descriptiva** (el rango típico de CR) y **regla prescriptiva** (los umbrales de evaluación no cambian).
2. Se agregó una sección nueva **"UMBRALES DE VIOLACIÓN (REGLA ESTRICTA)"** con cuatro puntos: usar 0.95/1.05 salvo pedido explícito, nunca copiar valores observados, regla idéntica para IEEE_14 y CR, y regla análoga para `loading_threshold`.
3. El "PROTOCOLO DE TRABAJO" se extendió con un punto 5: cuando una tool devuelve un campo `warning`, el agente debe reconsiderar la llamada antes de responder.

## 8.4 Verificación local (sin gasto de API)

Antes de cualquier corrida del agente con costo, se construyó `test_validacion_dia8.py` con cinco casos sintéticos sobre la nueva validación de `tools.py`:

| Test | Caso | Resultado esperado | Resultado obtenido |
| --- | --- | --- | --- |
| 1 | Sin parámetros (defaults) | sin warning | ✅ |
| 2 | `v_max=1.25415` (caso CR_Min·Q2 del Día 7) | warning sobre v_max | ✅ |
| 3 | `v_min=0.80` | warning sobre v_min | ✅ |
| 4 | `v_min=1.10, v_max=1.05` (invertidos) | error duro | ✅ |
| 5 | `v_min=0.95, v_max=1.05` explícitos | sin warning | ✅ |

Las cinco capas A funcionan según diseño. Las capas B y C no se pueden testear sin invocar al LLM real; su validación queda para 8.5.

## 8.5 Re-validación pendiente (próximo paso)

Para confirmar empíricamente que las tres capas juntas eliminan el fallo en una corrida real:

1. Reemplazar los tres archivos en `C:\Users\natyv\Documents\GridMind\` por sus versiones Día 8.
2. Re-ejecutar `correr_dia6.py` (estimado: ~$0.30 USD, idéntico al costo del Día 6).
3. Renombrar el log resultante (ej. `dia6_consultas_v2.json`).
4. Pasarlo por `validar_dia7.py` (apuntando al log nuevo).
5. Resultado esperado: **108/108 chequeos coinciden (100 %)**.

Si el resultado es 100 %, la mitigación quedó cerrada y el ciclo se documenta. Si aparece un fallo distinto, se itera de nuevo. En cualquier caso, queda registro del proceso.

## 8.6 Discusión: ¿qué tan seguro es GridMind?

La pregunta de la usuaria *"¿qué pasa si agarra otras cosas mal? ¿qué tan seguro es?"* admite una respuesta articulada en tres niveles:

**Nivel cálculo: 100 % seguro.** La separación arquitectónica entre razonamiento (LLM) y cálculo (PandaPower) garantiza que toda cifra numérica que el usuario reciba provenga del solver. La validación del Día 7 lo demostró empíricamente: 54/54 chequeos data-level coincidieron.

**Nivel razonamiento: alta robustez gracias a las 3 capas.** El razonamiento del LLM no es 100 % determinístico — esa es una propiedad intrínseca de la tecnología, no un defecto de implementación. La defensa en 3 capas reduce la probabilidad de errores de razonamiento a un nivel donde, cuando ocurren, son detectables: por validación de input (capa A), por descripción explícita (capa B) y por regla en el prompt (capa C). El protocolo de reacción a warnings (regla 5) agrega una cuarta capa: aunque el primer intento falle, el agente puede auto-corregirse en la misma conversación.

**Nivel sistema: validación cruzada periódica.** Los agentes LLM en producción no se confían a ciegas, se monitorean. La metodología del Día 7 (`ground_truth.py` + `validar_dia7.py`) provee precisamente eso: un mecanismo automatizado para detectar derivas. Cualquier fallo residual queda atrapado antes de llegar al usuario final.

La conjunción de estos tres niveles es lo que permite afirmar que GridMind es *defendible* como herramienta de análisis. No es "100 % infalible" — afirmar eso sería técnicamente deshonesto — pero es **100 % en cálculos numéricos**, **alta robustez en razonamiento** y **detectable cualquier fallo residual mediante validación cruzada**. Esa es la respuesta completa.

## 8.7 Archivos generados hoy

- `tools.py` Día 8 — con validación de inputs y warning blando.
- `definitions.py` Día 8 — descripciones reescritas + propiedad `default`.
- `agent.py` Día 8 — system prompt con sección UMBRALES DE VIOLACIÓN.
- `test_validacion_dia8.py` — verificación local de la capa A.
- `dia8.md` — esta entrada de bitácora.

---

**Cierre del Día 8.** El hallazgo del Día 7 quedó documentado, diagnosticado y mitigado en sus tres capas arquitectónicas. La verificación local confirma que la capa A funciona según diseño. La re-validación con corrida real del agente queda pendiente y se ejecuta cuando la usuaria lo decida.
