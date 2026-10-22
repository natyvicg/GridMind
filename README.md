# GridMind

Agente de inteligencia artificial para análisis de sistemas eléctricos de potencia. GridMind integra un LLM (Claude, Anthropic) con PandaPower para responder consultas técnicas en lenguaje natural sobre redes eléctricas, delegando todos los cálculos numéricos al simulador.

Desarrollado como Trabajo Final de Graduación (TFG) para la Licenciatura en Ingeniería Eléctrica, Universidad de Costa Rica. Versión actual: **1.4.1**.

## Arquitectura

GridMind usa el patrón **ReAct** (Reason + Act): el LLM razona sobre la consulta, decide qué herramienta de PandaPower usar, Python la ejecuta, y el resultado vuelve al LLM para que siga razonando o genere la respuesta final. El LLM nunca ejecuta código directamente ni inventa valores numéricos. El modelo se invoca con temperatura 0 y un máximo de 12 iteraciones por consulta.

### Salvaguardas

Además de la validación de umbrales (ver más abajo), el lazo del agente incluye desde la versión 1.4.1 una **salvaguarda determinista**: si la respuesta final contiene cifras de la red (un número con decimales y unidad eléctrica, o una fila de tabla con decimales) y la consulta no ejecutó ninguna herramienta, el lazo devuelve la respuesta al modelo una vez con la instrucción de ejecutar las herramientas; si el modelo insiste, la respuesta se entrega marcada como no verificada. La salvaguarda existe porque el historial de la conversación contiene solo texto, no resultados de herramientas, y en dos corridas del banco de consultas el modelo completó tablas de sobretensiones con barras inexistentes creyendo tener el resultado anterior en su contexto. Una regla en el prompt (versión 1.3.1) no bastó; la verificación en código sí.

```
Usuario → [consulta en lenguaje natural]
           ↓
       agent.py (loop ReAct con Claude)
           ↓
       tools.py (8 herramientas PandaPower)
           ↓
       PandaPower (cálculo real Newton-Raphson)
           ↓
       Respuesta con datos verificables
```

### Herramientas disponibles

| Herramienta | Función |
|---|---|
| `run_power_flow` | Carga red y ejecuta flujo de potencia |
| `get_voltage_violations` | Detecta barras con tensión fuera del rango operacional; en la red CR agrega el nombre de subestación |
| `get_overloaded_lines` | Detecta líneas y transformadores con cargabilidad por encima de un umbral (con umbral 0, lista la cargabilidad de todos) |
| `run_short_circuit` | Corriente de cortocircuito trifásica o bifásica, caso máximo o mínimo (IEC 60909) |
| `disconnect_line` | Desconecta una línea (simulación N-1) |
| `reconnect_line` | Reconecta una línea previamente desconectada |
| `modify_load` | Modifica una carga identificada por su barra (`bus_index`), con un factor de escala (`scale_factor`, 1.5 = +50 %) o valores absolutos; la herramienta resuelve la carga y hace la aritmética |
| `list_available_networks` | Lista todas las redes disponibles en el catálogo |

## Requisitos

- Python >= 3.10
- Conda (recomendado) o pip
- API key de Anthropic ([console.anthropic.com](https://console.anthropic.com))

## Instalación

```bash
# Crear el entorno
conda env create -f environment.yml

# Activar
conda activate gridmind

# Configurar API key (crear archivo .env en la raíz del proyecto)
echo ANTHROPIC_API_KEY=sk-ant-tu-clave-aqui > .env
```

Alternativa sin conda:

```bash
pip install -r requirements.txt
```

## Uso

> **Importante:** Siempre activar el entorno antes de ejecutar.

```bash
conda activate gridmind
python main.py
```

### Verificación rápida del entorno

```bash
python --version          # Debe ser >= 3.10
pip show pandapower       # Debe estar instalado
python -m tests.test_validacion_umbrales   # Umbrales e inputs, sin API key
python -m tests.test_cortocircuito         # Cortocircuito, sin API key
python -m tests.validar_agente             # Validación cruzada pre-mitigación (log v1)
python -m tests.validar_agente_v2          # Validación cruzada post-mitigación (log v2)
python -m tests.validar_agente_v3          # Validación cruzada sobre la versión 1.4.1 (log v3)
```

`test_validacion_umbrales` valida la lógica de inputs y umbrales de `tools.py`. `test_cortocircuito` valida la capa de datos de cortocircuito y la guarda de procedencia. Ninguna de las dos requiere API key ni conexión a internet; la segunda sí requiere los archivos Excel de la red CR.

Aparece un prompt interactivo donde podés escribir consultas en lenguaje natural. Ejemplos:

- *"¿Qué redes tenés disponibles?"*
- *"Carga la red IEEE_39 y dame un resumen del estado"*
- *"¿Qué pasa si desconecto la línea 1-5 en IEEE_14?"*
- *"Para la red CR_Min, ¿cuáles son las 5 peores violaciones de tensión?"*
- *"Corré un cortocircuito trifásico en CR_Med y dame las 5 barras con mayor corriente de falla"*

### Comandos especiales

| Comando | Función |
|---|---|
| `/ayuda` | Muestra la lista de comandos disponibles |
| `/redes` | Muestra las 18 redes disponibles con descripción |
| `/guardar` | Exporta la sesión completa a un archivo HTML con tema oscuro |
| `/historial` | Muestra las consultas hechas en la sesión actual |
| `/reset` | Descarga la red cargada y borra el historial |
| `/olvidar` | Borra el historial de conversación, conserva la red |
| `/salir` | Termina la sesión (también `/exit`, `/quit` o Ctrl+C) |

### Memoria de la conversación

GridMind recuerda las últimas 4 consultas de la sesión, así que entiende referencias como *"hacé lo mismo en IEEE_14"* o *"compará con lo anterior"*. Si una consulta queda ambigua incluso con el historial, el agente pregunta en vez de adivinar.

Solo se recuerdan los pares consulta/respuesta, nunca los resultados crudos de las herramientas: en la red CR un solo resultado puede traer cientos de filas y reenviarlo en cada iteración dispararía el costo sin aportar al razonamiento. Las respuestas largas se recortan a 1200 caracteres dentro del historial.

`/olvidar` corta el contexto sin perder el registro de la sesión: el HTML exportado sigue conteniendo todas las consultas.

La sesión exportada con `/guardar` incluye metadata por consulta y un resumen global. Se registran dos contadores de iteraciones distintos, porque miden cosas distintas: las **iteraciones del agente** son los ciclos de razonamiento del modelo (consulta a la API, ejecución de herramienta, retorno del resultado), y las **iteraciones NR** son las que le tomó converger al método de Newton-Raphson en PandaPower. El resumen incluye además el tiempo efectivo de cómputo, separado de la duración total de la sesión.

## Redes disponibles

GridMind incluye 18 redes listas para usar: 15 redes IEEE estándar de PandaPower y 3 escenarios de la red eléctrica de Costa Rica.

### Redes IEEE estándar

| Red | Barras | Descripción |
|---|---|---|
| `IEEE_4` | 4 | Grainger & Stevenson. Red mínima de prueba |
| `IEEE_5` | 5 | Red didáctica básica |
| `IEEE_6` | 6 | Wood & Wollenberg. Red didáctica |
| `IEEE_9` | 9 | WSCC. Red clásica de transmisión |
| `IEEE_14` | 14 | Red estándar académica de referencia |
| `IEEE_24_RTS` | 24 | IEEE Reliability Test System |
| `IEEE_30` | 30 | Red mediana de transmisión |
| `IEEE_33_BW` | 33 | Baran-Wu. Red de distribución radial |
| `IEEE_39` | 39 | New England. Red de transmisión con 10 generadores |
| `IEEE_57` | 57 | Red mediana-grande de transmisión |
| `IEEE_89_PEGASE` | 89 | PEGASE. Red europea de transmisión |
| `IEEE_118` | 118 | Benchmark clásico de transmisión |
| `IEEE_145` | 145 | Red grande con múltiples niveles de tensión |
| `IEEE_200` | 200 | Illinois. Red grande de transmisión |
| `IEEE_300` | 300 | Red muy grande, prueba de escalabilidad |

### Red eléctrica de Costa Rica

| Red | Barras | Descripción |
|---|---|---|
| `CR_Min` | 524 | Demanda mínima (marzo 2023) |
| `CR_Med` | 524 | Demanda media (marzo 2023) |
| `CR_Max` | 524 | Demanda máxima (marzo 2023) |

### Particularidades de la red CR

- Los índices de barra son enteros grandes (50000+), no aplica convención IEEE 1-indexed.
- Opera con tensiones fuera del rango estándar 0.95-1.05 pu por diseño operativo (Vmin típico ~0.75-0.81 pu, Vmax ~1.20-1.25 pu). Esto es una característica del modelo, no un error.
- 11 de 524 barras no tienen resultado en `res_bus` por despacho operativo (3 barras cuyas 4 unidades generadoras no están despachadas + 8 devanados terciarios de transformadores fuera de servicio). Las herramientas filtran NaN automáticamente.
- Las interconexiones con Nicaragua y Panamá se representan como cinco fuentes ideales en barras de frontera de 230 kV (decisión de `red_cr.py`; el Excel declara una única barra de referencia interna). `scripts/sensibilidad_frontera.py` compara ambas representaciones: en CR_Max las subtensiones pasan de 29 a 56 con la referencia interna. Los conteos de violaciones dependen de esta elección.
- El Excel declara límites normales de 0.90 y 1.10 pu; GridMind evalúa violaciones con 0.95 y 1.05 pu, criterio de planificación.

## Cortocircuito y procedencia de datos

`run_short_circuit` calcula la corriente inicial simétrica de cortocircuito Ik" según IEC 60909. Es un cálculo algebraico de red, del mismo tipo que el flujo de carga: no hay integración en el tiempo, por lo que se mantiene dentro del alcance de análisis en estado estacionario.

El cálculo requiere la impedancia de las fuentes, que el flujo de carga no utiliza. Esa diferencia determina en qué redes se puede calcular:

| Red | Datos de cortocircuito | Comportamiento de la herramienta |
|---|---|---|
| `CR_Min`, `CR_Med`, `CR_Max` | Reactancia de las 108 máquinas, del modelo PSS/E de origen | Calcula con datos del modelo |
| Redes IEEE | Ninguno: se publicaron como casos de flujo de carga | Informa qué parámetros faltan y no calcula |

En las redes IEEE la herramienta **no estima valores**: devuelve la lista de parámetros ausentes y sugiere usar una red CR. Solo si el usuario lo pide de forma explícita (`parametros_tipicos=true`) se calcula con valores de literatura, y el resultado se devuelve rotulado como basado en supuestos, con un warning. Además, una guarda de plausibilidad detecta modelos cuyas tensiones nominales son marcadores de posición — IEEE 14 declara barras en 0.208 kV — y avisa que el resultado no es físicamente significativo.

### Corrección de mapeo en la red CR

La hoja `Generator Data` del Excel sigue el registro estándar de PSS/E, donde la columna `X Source (pu)` es la impedancia de máquina y `Xtran (pu)` la del transformador elevador. `red_cr.py` asigna a `xdss_pu` la columna del transformador, que en este modelo está en cero para las 108 unidades, de modo que la reactancia real nunca entra a la red.

El error es silencioso en flujo de carga, porque `runpp` no usa `xdss_pu`. Se vuelve bloqueante en cortocircuito. `datos_cortocircuito.py` remapea la columna correcta sobre la red ya construida, verificando la alineación barra por barra antes de escribir, sin modificar `red_cr.py` ni los Excel.

### Supuestos declarados

- **Resistencia de máquina:** el modelo trae `R source (pu)` en cero; se asume R = X / 20.
- **Tensión nominal de máquina:** se usa la de la barra de conexión, al no haber campo explícito.
- **Factor de potencia nominal de máquina:** 0.85 (no está en el modelo). Entre 0.80 y 0.95 la corriente máxima varía 2 %.
- **Temperatura final de conductor (caso mínimo):** 80 °C. Entre 20 y 120 °C la corriente máxima varía 0.03 %.
- **Interconexiones:** `red_cr.py` modela las conexiones con Nicaragua y Panamá como cinco fuentes ideales en barras que el modelo original clasifica como barras pasivas. Su potencia de cortocircuito se expone como parámetro (2000 MVA y R/X = 0.1 por defecto, supuestos sin respaldo en datos públicos). `scripts/sensibilidad_cortocircuito.py` cuantifica el efecto: variar el supuesto de 500 a 20 000 MVA cambia la corriente media en las barras de interconexión de 6.5 a 76.9 kA, pero mueve la mediana del resto de la red solo un 3.1 %.

Los scripts de sensibilidad usan `pandas.DataFrame.to_markdown`, que requiere el paquete `tabulate` (`pip install tabulate`); escriben su tabla en un `.xlsx` antes de imprimirla.

## Escenarios de validación

`escenarios.py` genera automáticamente 4 escenarios estándar (ORIGINAL, BASE, SUBTENSIÓN, SOBRECARGA) para cualquiera de las 15 redes IEEE, con ground truth calculado directamente desde PandaPower. Además incluye 7 escenarios curados (E1-E7) diseñados a mano para IEEE 14 y Costa Rica.

De las 15 redes IEEE, 9 producen los 4 escenarios viables; IEEE 145 y 300 fallan por problemas estructurales de tensión en sus parámetros de fábrica (no son bugs de GridMind).

## Estructura del proyecto

```
GridMind/
├── agent.py                    # Loop ReAct + system prompt
├── tools.py                    # 8 herramientas PandaPower + dispatcher
├── definitions.py              # JSON Schema de herramientas (Anthropic)
├── main.py                     # CLI interactiva con comandos especiales
├── escenarios.py               # Escenarios genéricos (15 IEEE) + curados (E1-E7)
├── red_cr.py                   # Constructor original de la red CR (no modificar)
├── red_cr_loader.py            # Adaptador para cargar red CR desde Excel
├── datos_cortocircuito.py      # Capa de datos de cortocircuito (IEC 60909)
├── red_cr_transmisión.py       # Modelo de transmisión CR (referencia)
├── Base_CR_*_2023-Marzo.xlsx    # Datos de demanda CR (Min, Med, Max)
├── sensibilidad_frontera.xlsx  # Salida de scripts/sensibilidad_frontera.py
├── environment.yml             # Entorno conda reproducible
├── requirements.txt            # Dependencias pip
├── .gitignore
│
├── docs/                       # Documentación del TFG
│   ├── Propuesta_TFG_Natalia_Victor_B98438.pdf
│
├── tests/                      # Validación y pruebas
│   ├── ground_truth.py             # Cálculos directos PandaPower para validación
│   ├── test_validacion_umbrales.py # Tests de validación de inputs (sin API)
│   ├── test_cortocircuito.py       # Tests de la capa de cortocircuito (sin API)
│   ├── correr_bateria.py           # Batería automatizada v1 (9 consultas CR)
│   ├── correr_bateria_v2.py        # Batería automatizada v2 (post-corrección)
│   ├── correr_bateria_v3.py        # Batería automatizada v3 (versión 1.4.1)
│   ├── validar_agente.py           # Validación cruzada agente vs PandaPower
│   ├── validar_agente_v2.py        # Re-validación post-corrección de umbrales
│   └── validar_agente_v3.py        # Validación sobre la versión 1.4.1
│
├── scripts/                    # Diagnóstico y análisis (no son core)
│   ├── validar_red_cr.py           # Validación inicial de la red CR
│   ├── diagnosticar_barras_cr.py   # Diagnóstico de las 11 barras sin resultado
│   ├── analizar_barras_aisladas.py # Análisis detallado de barras aisladas
│   ├── consolidar_escenarios.py    # (histórico — depende de metricas.py, ya obsoleto)
│   ├── ejecutar_escenarios_ieee14.py # (histórico — actualizar import a escenarios.py)
│   ├── probar_escenarios_genericos.py # Prueba de escenarios genéricos
│   ├── sensibilidad_cortocircuito.py # Sensibilidad al supuesto de S_cc
│   ├── sensibilidad_frontera.py    # Dos representaciones de las interconexiones
│   └── procesar_datos.py           # Procesamiento de datos CR
│
└── logs/                       # Sesiones (HTML) y logs de validación (JSON)

```

Archivos generados automáticamente (excluidos de Git via `.gitignore`):

- `_Backup_*_2023-Marzo.xlsx` — Copias permanentes de los Excel CR, creadas por `red_cr_loader.py` en la primera ejecución. No borrar manualmente.
- `Resultados*.xlsx` — Salida de `red_cr.py` al construir la red.
- `.env` — API key de Anthropic (crear manualmente).

> **Nota sobre scripts históricos:** Los scripts en `scripts/` fueron herramientas de desarrollo usadas durante la construcción del proyecto. Algunos (`consolidar_escenarios.py`, `ejecutar_escenarios_ieee14.py`) dependen de módulos que ya no existen porque su funcionalidad fue absorbida por `escenarios.py`. No deben ejecutarse sin revisión previa.

## Resultados de validación

La validación cruzada compara las respuestas del agente contra cálculos directos de PandaPower en tres niveles:

El arnés corre 9 consultas: 3 escenarios CR × 3 preguntas (resumen, violaciones de tensión, sobrecargas), y produce 96 chequeos en tres niveles.

| Nivel | Qué verifica | Pre-mitigación | Post-mitigación | Versión 1.4.1 |
|---|---|---|---|---|
| Tool | ¿Llamó las herramientas correctas, con los argumentos correctos? | 17/18 | 18/18 | 18/18 |
| Data | ¿Los números coinciden con PandaPower? | 54/54 | 54/54 | 54/54 |
| Response | ¿La respuesta final refleja los datos? | 24/24 | 24/24 | 24/24 |
| **Total** | | **95/96 (98.96%)** | **96/96 (100%)** | **96/96 (100%)** |

Los tres resultados son reproducibles sin API key, porque la validación se corre sobre los logs de las baterías ya ejecutadas: `logs/log_bateria_v1.json`, `logs/log_bateria_v2.json` y `logs/log_bateria_v3.json` (20 de octubre de 2026, 0.57 USD). Las salidas quedan en `logs/log_validacion_v1.json`, `log_validacion_v2.json` y `log_validacion_v3.json`. La referencia la calcula `tests/ground_truth.py` con el mismo cargador que usa el agente (backups de los Excel, nunca los originales).

### Banco de consultas

Además de la batería, un banco de 21 consultas (6 sobre IEEE_14 e IEEE_118 y 15 sobre los tres escenarios CR: resumen, violaciones de tensión, cargabilidad, contingencia N-1, cortocircuito y comparación entre escenarios) se ejecutó como sesión completa cuatro veces, sobre las versiones 1.3.0, 1.3.1, 1.4.0 y 1.4.1. Las sesiones están en `logs/sesion_2026-10-19_1456.html`, `sesion_2026-10-19_1611.html`, `sesion_2026-10-19_1736.html` y `sesion_2026-10-20_0054.html`. Las tres primeras contienen los errores que motivaron cada corrección (respuestas sin herramienta con barras inexistentes; carga equivocada modificada); en la cuarta todas las cifras de herramienta coinciden con PandaPower. Los HTML listan las herramientas invocadas pero no sus argumentos, que solo se ven en la consola.

### Hallazgo: threshold drift

Durante la validación se documentó un modo de falla donde el LLM confunde valores observados (el Vmax de la red) con umbrales operacionales (1.05 pu), y en consecuencia no busca sobretensiones. Se mitigó con tres capas: validación runtime en `tools.py`, descripciones explícitas en `definitions.py`, y convención de umbrales en el system prompt de `agent.py`.

La validación pre-mitigación falla en **un solo chequeo de los 96**, y es exactamente este:

```
CR_Min · Q2_subtensiones | get_voltage_violations.v_max | agente = 1.25415 | esperado = 1.05
```

El detalle metodológico importa: la falla aparece únicamente en el nivel **tool**, mientras que los niveles data y response quedan en 54/54 y 24/24. La razón es que el agente reportó correctamente los números que obtuvo — simplemente nunca buscó sobretensiones. Comparar solo cifras contra ground truth no habría detectado nada, porque las cifras eran internamente consistentes. Por eso el error es de razonamiento y no de cálculo, y por eso hacen falta los tres niveles: uno solo no lo encuentra.

## Limitaciones conocidas

- **Alcance de simulación**: análisis en estado estacionario. Incluye flujo de carga y cortocircuito según IEC 60909, ambos cálculos algebraicos de red. No incluye estudios en dominio del tiempo — estabilidad electromecánica ni transitorios electromagnéticos — ni flujo óptimo de potencia.
- **Datos de cortocircuito en redes IEEE**: los casos de prueba IEEE no incluyen impedancia de fuente, por lo que el cortocircuito solo se calcula con datos reales sobre la red de Costa Rica. La herramienta lo informa explícitamente en vez de estimar.
- **Potencia de cortocircuito de las interconexiones**: no está en el modelo de origen y se trata como parámetro declarado. Su efecto es local (ver el análisis de sensibilidad).
- **Tensiones CR fuera de rango**: la red CR opera con tensiones que violan el rango estándar. Esto es una propiedad del modelo y se documenta como limitación reconocida.
- **Sin memoria entre sesiones**: el historial vive solo mientras la sesión está abierta y cubre las últimas 4 consultas. Al cerrar `main.py` se pierde; el registro exportado con `/guardar` queda, pero no se recarga.
- **Determinismo del LLM**: las respuestas del agente no son determinísticas ni con temperatura 0 (la misma consulta se resolvió bien en tres corridas y mal en una). Las salvaguardas en código reducen el efecto sobre las cifras; la presentación (orden de listas combinadas, inferencias sobre nombres) todavía depende del modelo.
- **Resumen del flujo**: `run_power_flow` calcula la cargabilidad máxima de transformadores solo sobre los de dos devanados y no expresa las barras sin resultado de una contingencia como carga no servida. `get_overloaded_lines` sí cubre los de tres devanados.
- **Archivo Max hardcoded**: `red_cr.py` tiene hardcoded el nombre `Base_CR_Max_2023-Marzo.xlsx`. El loader (`red_cr_loader.py`) maneja esto con backup permanente y restauración automática. No borrar `_Backup_Max_2023-Marzo.xlsx`.

## Historial de versiones

| Versión | Revisión | Cambios |
|---|---|---|
| 1.3.0 | `ae4cd1a` | Cortocircuito IEC 60909 (`datos_cortocircuito.py`, `run_short_circuit`), scripts de sensibilidad, tests |
| 1.3.1 | `a97c681` | Regla de historial en el prompt, unidades de desviación, nombres de subestación en `get_voltage_violations` |
| 1.4.0 | `fe17d9b` | `modify_load` por barra y factor de escala, temperatura 0, reglas de protocolo y formato |
| 1.4.1 | `3ecdcc3` | Salvaguarda del lazo contra respuestas con cifras sin herramienta; regla de procedencia de cifras |

Los registros de las corridas se publicaron en las revisiones `2cf0b91`, `446d485` y `875b00f`.

## Autor

Natalia Víctor Gallardo — B98438, Universidad de Costa Rica.
