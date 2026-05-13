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
       tools.py (6 herramientas PandaPower)
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

### Chat interactivo

```bash
python main.py
```

Aparece un prompt donde podés escribir consultas en lenguaje natural. Ejemplos:

- *"Carga la red IEEE_14 y dame un resumen del estado"*
- *"¿Qué pasa si desconecto la línea 1-5?"*
- *"Para la red CR_Min, ¿cuántas barras presentan violaciones de tensión?"*

Comandos especiales: `/reset` (reiniciar red) | `/salir` (terminar).

### Batería de pruebas automatizada

```bash
# Correr 9 consultas sobre los 3 escenarios CR (~$0.37 USD)
python correr_bateria_v2.py

# Validar resultados contra PandaPower (sin costo)
python validar_agente_v2.py

# Tests de validación de umbrales (sin costo, sin API key)
python test_validacion_umbrales.py
```

## Redes disponibles

| Red | Barras | Descripción |
|---|---|---|
| `IEEE_14` | 14 | Red académica estándar IEEE 14 barras |
| `CR_Min` | 524 | Red eléctrica de Costa Rica, demanda mínima (marzo 2023) |
| `CR_Med` | 524 | Red eléctrica de Costa Rica, demanda media (marzo 2023) |
| `CR_Max` | 524 | Red eléctrica de Costa Rica, demanda máxima (marzo 2023) |

### Particularidades de la red CR

- Los índices de barra son enteros grandes (50000+), no aplica convención IEEE 1-indexed.
- Opera con tensiones fuera del rango estándar 0.95-1.05 pu por diseño operativo (Vmin típico ~0.75-0.81 pu, Vmax ~1.20-1.25 pu). Esto es una característica del modelo, no un error.
- 11 de 524 barras no tienen resultado en `res_bus` por despacho operativo (3 unidades no despachadas + 8 devanados terciarios desactivados). Las herramientas filtran NaN automáticamente.

## Estructura del proyecto

```
GridMind/
├── agent.py                      # Loop ReAct + system prompt
├── tools.py                      # 6 herramientas PandaPower + dispatcher
├── definitions.py                # JSON Schema de herramientas (Anthropic/OpenAI)
├── main.py                       # CLI interactiva
├── red_cr_loader.py              # Adaptador para cargar red CR desde Excel
├── red_cr.py                     # Constructor original de la red CR (no modificar)
├── ground_truth.py               # Cálculos directos PandaPower para validación
├── escenarios_ieee14.py          # 4 escenarios IEEE 14 (original/base/subtensión/sobrecarga)
├── escenarios.py                 # Builders de escenarios para tabla maestra
├── correr_bateria_v2.py          # Batería automatizada de 9 consultas sobre CR
├── validar_agente.py             # Validación cruzada agente vs PandaPower
├── validar_agente_v2.py          # Re-validación post-corrección de umbrales
├── test_validacion_umbrales.py   # Tests de la validación de inputs (sin API)
├── ejecutar_escenarios_ieee14.py # Genera unifilares y tabla resumen IEEE 14
├── consolidar_escenarios.py      # Tabla maestra de 7 escenarios (histórico)
├── validar_red_cr.py             # Validación inicial de la red CR
├── diagnosticar_barras_cr.py     # Diagnóstico de las 11 barras sin resultado
├── analizar_barras_aisladas.py   # Análisis detallado de barras aisladas
├── red_cr_transmisión.py         # Modelo de transmisión CR (referencia)
├── Procesar_datos.py             # Procesamiento de datos CR (referencia)
├── requirements.txt              # Dependencias pip (freeze completo)
├── environment.yml               # Entorno conda reproducible
├── .env                          # API key (NO incluido en Git)
├── .gitignore                    # Exclusiones de Git
├── Base_CR_Min_2023-Marzo.xlsx   # Datos de demanda mínima CR
├── Base_CR_Med_2023-Marzo.xlsx   # Datos de demanda media CR
├── Base_CR_Max_2023-Marzo.xlsx   # Datos de demanda máxima CR
├── _Backup_Max_2023-Marzo.xlsx   # Backup permanente del Max original
├── logs/                         # Logs de corridas y validación
│   ├── log_bateria_v1.json       # Primera corrida (con hallazgo de umbrales)
│   ├── log_bateria_v2.json       # Segunda corrida (post-corrección)
│   ├── log_bateria_v1.md         # Versión legible de la primera corrida
│   └── log_validacion_v2.json    # Validación cruzada: 96/96 chequeos (100%)
└── docs/                         # Documentación del TFG (bitácoras, propuesta)
```

## Resultados de validación

La validación cruzada compara las respuestas del agente contra cálculos directos de PandaPower en tres niveles:

| Nivel | Qué verifica | Resultado |
|---|---|---|
| Tool | ¿Llamó las herramientas correctas? | 18/18 (100%) |
| Data | ¿Los números coinciden con PandaPower? | 54/54 (100%) |
| Response | ¿La respuesta final refleja los datos? | 24/24 (100%) |
| **Total** | | **96/96 (100%)** |

Costo promedio por consulta: ~$0.04 USD (Claude Sonnet 4.6).

## Limitaciones conocidas

- **Alcance de simulación**: flujo de carga estacionario únicamente. No incluye estudios dinámicos, transitorios, cortocircuito ni flujo óptimo de potencia.
- **Redes soportadas**: IEEE 14 y CR (Min/Med/Max). Para agregar redes nuevas, extender `AVAILABLE_NETWORKS` en `tools.py` y el catálogo en `definitions.py`.
- **Tensiones CR fuera de rango**: la red CR opera con tensiones que violan el rango estándar. Esto es una propiedad del modelo y se documenta como limitación reconocida.
- **Determinismo del LLM**: las respuestas del agente no son 100% determinísticas. La validación de umbrales (3 capas) y la validación cruzada periódica mitigan este riesgo.
- **Archivo Max hardcoded**: `red_cr.py` tiene hardcoded el nombre `Base_CR_Max_2023-Marzo.xlsx`. El loader (`red_cr_loader.py`) maneja esto con backup permanente y restauración automática. No borrar `_Backup_Max_2023-Marzo.xlsx`.

## Autor

Natalia Víctor Sandoval — B98438, Universidad de Costa Rica.
