# GridMind

Agente de inteligencia artificial para análisis de sistemas eléctricos de potencia. GridMind integra un LLM (Claude, Anthropic) con PandaPower para responder consultas técnicas en lenguaje natural sobre redes eléctricas, delegando todos los cálculos numéricos al simulador.

Desarrollado como Trabajo Final de Graduación (TFG) para la Licenciatura en Ingeniería Eléctrica, Universidad de Costa Rica.

## Arquitectura

GridMind usa el patrón **ReAct** (Reason + Act): el LLM razona sobre la consulta, decide qué herramienta de PandaPower usar, Python la ejecuta, y el resultado vuelve al LLM para que siga razonando o genere la respuesta final. El LLM nunca ejecuta código directamente ni inventa valores numéricos.

```
Usuario → [consulta en lenguaje natural]
           ↓
       agent.py (loop ReAct con Claude)
           ↓
       tools.py (7 herramientas PandaPower)
           ↓
       PandaPower (cálculo real Newton-Raphson)
           ↓
       Respuesta con datos verificables
```

### Herramientas disponibles

| Herramienta | Función |
|---|---|
| `run_power_flow` | Carga red y ejecuta flujo de potencia |
| `get_voltage_violations` | Detecta barras con tensión fuera del rango operacional |
| `get_overloaded_lines` | Detecta líneas con cargabilidad excesiva |
| `disconnect_line` | Desconecta una línea (simulación N-1) |
| `reconnect_line` | Reconecta una línea previamente desconectada |
| `modify_load` | Modifica potencia activa/reactiva de una carga |
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

```bash
python main.py
```

Aparece un prompt interactivo donde podés escribir consultas en lenguaje natural. Ejemplos:

- *"¿Qué redes tenés disponibles?"*
- *"Carga la red IEEE_39 y dame un resumen del estado"*
- *"¿Qué pasa si desconecto la línea 1-5 en IEEE_14?"*
- *"Para la red CR_Min, ¿cuáles son las 5 peores violaciones de tensión?"*

### Comandos especiales

| Comando | Función |
|---|---|
| `/ayuda` | Muestra la lista de comandos disponibles |
| `/redes` | Muestra las 18 redes disponibles con descripción |
| `/guardar` | Exporta la sesión completa a un archivo HTML con tema oscuro |
| `/historial` | Muestra las consultas hechas en la sesión actual |
| `/reset` | Descarga la red cargada (empezar de cero) |
| `/salir` | Termina la sesión (también `/exit`, `/quit` o Ctrl+C) |

La sesión exportada con `/guardar` incluye metadata por consulta (herramientas usadas, iteraciones, tokens, costo, tiempo) y un resumen global de la sesión.

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
- 11 de 524 barras no tienen resultado en `res_bus` por despacho operativo (3 unidades no despachadas + 8 devanados terciarios desactivados). Las herramientas filtran NaN automáticamente.

## Escenarios de validación

`escenarios.py` genera automáticamente 4 escenarios estándar (ORIGINAL, BASE, SUBTENSIÓN, SOBRECARGA) para cualquiera de las 15 redes IEEE, con ground truth calculado directamente desde PandaPower. Además incluye 7 escenarios curados (E1-E7) diseñados a mano para IEEE 14 y Costa Rica.

De las 15 redes IEEE, 9 producen los 4 escenarios viables; IEEE 145 y 300 fallan por problemas estructurales de tensión en sus parámetros de fábrica (no son bugs de GridMind).

## Estructura del proyecto

```
GridMind/
├── agent.py                    # Loop ReAct + system prompt
├── tools.py                    # 7 herramientas PandaPower + dispatcher
├── definitions.py              # JSON Schema de herramientas (Anthropic/OpenAI)
├── main.py                     # CLI interactiva con comandos especiales
├── escenarios.py               # Escenarios genéricos (15 IEEE) + curados (E1-E7)
├── red_cr.py                   # Constructor original de la red CR (no modificar)
├── red_cr_loader.py            # Adaptador para cargar red CR desde Excel
├── red_cr_transmisión.py       # Modelo de transmisión CR (referencia)
├── Base_CR_*_2023Marzo.xlsx    # Datos de demanda CR (Min, Med, Max)
├── environment.yml             # Entorno conda reproducible
├── requirements.txt            # Dependencias pip
├── .gitignore
│
├── docs/                       # Documentación del TFG
│   ├── Propuesta_TFG_Natalia_Victor_B98438.pdf
│   └── bitacora_mitigacion_umbrales.md
│
├── tests/                      # Validación y pruebas
│   ├── ground_truth.py             # Cálculos directos PandaPower para validación
│   ├── test_validacion_umbrales.py # Tests de validación de inputs (sin API)
│   ├── correr_bateria.py           # Batería automatizada v1 (9 consultas CR)
│   ├── correr_bateria_v2.py        # Batería automatizada v2 (post-corrección)
│   ├── validar_agente.py           # Validación cruzada agente vs PandaPower
│   └── validar_agente_v2.py        # Re-validación post-corrección de umbrales
│
├── scripts/                    # Diagnóstico y análisis (no son core)
│   ├── validar_red_cr.py           # Validación inicial de la red CR
│   ├── diagnosticar_barras_cr.py   # Diagnóstico de las 11 barras sin resultado
│   ├── analizar_barras_aisladas.py # Análisis detallado de barras aisladas
│   ├── consolidar_escenarios.py    # Tabla maestra de 7 escenarios (histórico)
│   ├── ejecutar_escenarios_ieee14.py # Genera unifilares y tabla resumen IEEE 14
│   ├── probar_escenarios_genericos.py # Prueba de escenarios genéricos
│   └── procesar_datos.py           # Procesamiento de datos CR
│
└── logs/                       # Sesiones y logs de validación
    ├── log_bateria_v1.json         # Primera corrida (con hallazgo de umbrales)
    ├── log_bateria_v2.json         # Segunda corrida (post-corrección)
    └── log_validacion_v2.json      # Validación cruzada: 96/96 (100%)
```

Archivos generados automáticamente (excluidos de Git via `.gitignore`):

- `_Backup_*_2023-Marzo.xlsx` — Copias permanentes de los Excel CR, creadas por `red_cr_loader.py` en la primera ejecución. No borrar manualmente.
- `Resultados*.xlsx` — Salida de `red_cr.py` al construir la red.
- `.env` — API key de Anthropic (crear manualmente).

## Resultados de validación

La validación cruzada compara las respuestas del agente contra cálculos directos de PandaPower en tres niveles:

| Nivel | Qué verifica | Resultado |
|---|---|---|
| Tool | ¿Llamó las herramientas correctas? | 18/18 (100%) |
| Data | ¿Los números coinciden con PandaPower? | 54/54 (100%) |
| Response | ¿La respuesta final refleja los datos? | 24/24 (100%) |
| **Total** | | **96/96 (100%)** |

### Hallazgo: threshold drift

Durante la validación se documentó un modo de falla donde el LLM confunde valores observados (Vmax de la red) con umbrales operacionales (1.05 pu), reportando 0 violaciones cuando sí las hay. Se mitigó con tres capas: validación runtime en `tools.py`, descripciones explícitas en `definitions.py`, y convención de umbrales en el system prompt de `agent.py`.

## Limitaciones conocidas

- **Alcance de simulación**: flujo de carga estacionario únicamente. No incluye estudios dinámicos, transitorios, cortocircuito ni flujo óptimo de potencia.
- **Tensiones CR fuera de rango**: la red CR opera con tensiones que violan el rango estándar. Esto es una propiedad del modelo y se documenta como limitación reconocida.
- **Determinismo del LLM**: las respuestas del agente no son 100% determinísticas. La validación de umbrales (3 capas) y la validación cruzada periódica mitigan este riesgo.
- **Archivo Max hardcoded**: `red_cr.py` tiene hardcoded el nombre `Base_CR_Max_2023-Marzo.xlsx`. El loader (`red_cr_loader.py`) maneja esto con backup permanente y restauración automática. No borrar `_Backup_Max_2023-Marzo.xlsx`.

## Autor

Natalia Víctor Gallardo — B98438, Universidad de Costa Rica.
