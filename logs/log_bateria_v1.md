# Día 6 — Logs de consultas GridMind sobre red CR

Modelo: claude-sonnet-4-6  ·  Escenarios: ['CR_Min', 'CR_Med', 'CR_Max']


## Totales

- Consultas exitosas: 9 / 9
- Tokens input totales: 67,907
- Tokens output totales: 6,438
- Costo total estimado: $0.3003 USD


---

## CR_Min · Q1_resumen

**Consulta:** Carga la red CR_Min y reporta Vmin, Vmax (en pu) y la carga máxima de línea (en %). Indícame también cuántas barras tiene la red y cuántas tienen resultado válido.


**Iteraciones:** 2  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 9.9 s


**Usage:** in=5100, out=543, costo=$0.0234


**Tool calls:**

- `run_power_flow({'network': 'CR_Min'})`
  - resumen: `{'network': 'CR_Min', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.8085435788072961, 'v_max_pu': 1.2541210827568323, 'max_line_loading_percent': 71.65566828837551, 'max_trafo_loading_percent': 88.53500275628622}`

**Respuesta final:**

```
Aquí tienes el resumen completo del flujo de potencia para la red **CR_Min** (demanda mínima de Costa Rica):

---

### ⚡ Resultado del Flujo de Potencia — CR_Min

| Parámetro | Valor |
|---|---|
| **Convergencia** | ✅ Newton-Raphson convergió |
| **Total de barras** | 524 |
| **Barras con resultado válido** | 513 |
| **Barras sin resultado** | 11 *(3 unidades no despachadas + 8 devanados terciarios desactivados)* |
| **Tensión mínima (Vmin)** | **0.8085 pu** |
| **Tensión máxima (Vmax)** | **1.2541 pu** |
| **Carga máxima de línea** | **71.66 %** |
| **Carga máxima de transformador** | **88.54 %** |

---

### 📋 Notas importantes

- **Perfil de tensiones fuera del rango estándar (0.95–1.05 pu):** Tanto el Vmin (~0.81 pu) como el Vmax (~1.25 pu) violan los límites convencionales. Esto es una **condición conocida del modelo operativo de la red CR**, no un error numérico; la red opera con rangos de tensión más amplios por diseño.
- **11 barras sin resultado** no son fallas de cálculo: corresponden a equipos fuera de servicio en el escenario de demanda mínima.
- **Sin sobrecargas:** Tanto líneas (71.66 %) como transformadores (88.54 %) se mantienen **por debajo del 100 %**, lo que indica que en el escenario de demanda mínima no hay elementos en sobrecarga.
```


---

## CR_Min · Q2_subtensiones

**Consulta:** En la red CR_Min, ¿cuántas barras presentan subtensión (< 0.95 pu)? Lista las 5 barras con menor tensión, indicando su índice de barra y el valor de tensión en pu.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 18.2 s


**Usage:** in=8685, out=934, costo=$0.0401


**Tool calls:**

- `run_power_flow({'network': 'CR_Min'})`
  - resumen: `{'network': 'CR_Min', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.8085435788072961, 'v_max_pu': 1.2541210827568323, 'max_line_loading_percent': 71.65566828837551, 'max_trafo_loading_percent': 88.53500275628622}`
- `get_voltage_violations({'v_min': 0.95, 'v_max': 1.25415, 'limit': 500})`
  - resumen: `{'network': 'CR_Min', 'v_min_threshold': 0.95, 'v_max_threshold': 1.25415, 'n_violations_total': 17, 'n_subtension': 17, 'n_sobretension': 0, 'limit_applied': 500}`
  - violations[:3]: `[{'bus_index': 50280, 'vm_pu': 0.8085435788072961, 'tipo': 'subtension'}, {'bus_index': 58312, 'vm_pu': 0.8599376003883082, 'tipo': 'subtension'}, {'bus_index': 54080, 'vm_pu': 0.9205299207793154, 'tipo': 'subtension'}]`

**Respuesta final:**

```
Aquí está el análisis completo para la red **CR_Min** (demanda mínima, 524 barras):

---

## 📊 Resultado del Flujo de Potencia — CR_Min

| Parámetro | Valor |
|---|---|
| Convergencia | ✅ Sí |
| Barras totales con resultado | 513 / 524 |
| Tensión mínima global | 0.8085 pu |
| Tensión máxima global | 1.2541 pu |

> ⚠️ **Nota sobre el modelo CR:** Este modelo opera por diseño fuera del rango estándar (0.95–1.05 pu), con tensiones que típicamente oscilan entre ~0.75 y ~1.25 pu. Las 11 barras sin resultado corresponden a unidades no despachadas y devanados terciarios desactivados; no son errores numéricos.

---

## 🔴 Barras en Subtensión (< 0.95 pu)

**Total de barras con subtensión: 17**

### Las 5 barras con menor tensión:

| # | Índice de Barra | Tensión (pu) | Desviación vs. 0.95 pu |
|---|---|---|---|
| 1 | **50280** | **0.8085 pu** | −0.1415 pu |
| 2 | **58312** | **0.8599 pu** | −0.0901 pu |
| 3 | **54080** | **0.9205 pu** | −0.0295 pu |
| 4 | **58336** | **0.9208 pu** | −0.0292 pu |
| 5 | **50130** | **0.9283 pu** | −0.0667 pu |

---

### 🔍 Observaciones clave

- La barra **50280** es la más crítica, con una tensión de apenas **0.8085 pu**, casi **14.2 puntos porcentuales** por debajo del límite inferior operativo (0.95 pu).
- La barra **58312** también presenta un nivel severo: **0.8599 pu** (~9 puntos por debajo del límite).
- Las barras 54080, 58336 y 50130 están más cerca del límite, con desviaciones entre 3 y 7 puntos porcentuales.
- En total, el **3.3% de las barras con resultado** (17 de 513) presentan subtensión bajo el umbral estándar de 0.95 pu.
```


---

## CR_Min · Q3_sobrecargas

**Consulta:** En la red CR_Min, ¿hay líneas sobrecargadas (carga > 100%)? Si las hay, dime cuántas son en total y lista hasta 5 con el índice de línea, las barras de extremo y el porcentaje de carga.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 13.7 s


**Usage:** in=8053, out=637, costo=$0.0337


**Tool calls:**

- `run_power_flow({'network': 'CR_Min'})`
  - resumen: `{'network': 'CR_Min', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.8085435788072961, 'v_max_pu': 1.2541210827568323, 'max_line_loading_percent': 71.65566828837551, 'max_trafo_loading_percent': 88.53500275628622}`
- `get_overloaded_lines({'loading_threshold': 100, 'limit': 20})`
  - resumen: `{'network': 'CR_Min', 'loading_threshold_percent': 100, 'n_overloaded_total': 0, 'limit_applied': 20}`
  - overloaded[:3]: `[]`

**Respuesta final:**

```
¡Excelente noticia! Aquí está el resumen completo del análisis:

---

## 🔍 Análisis de Sobrecarga de Líneas — Red CR_Min

### Resultado del Flujo de Potencia
| Parámetro | Valor |
|---|---|
| Convergencia | ✅ Sí |
| Barras totales | 524 |
| Líneas totales | 137 |
| Transformadores | 256 |
| Carga máxima en líneas | **71.66 %** |
| Carga máxima en transformadores | **88.54 %** |

---

### ¿Líneas sobrecargadas (> 100%)?

## ✅ No hay ninguna línea sobrecargada.

En el escenario de **demanda mínima (CR_Min)**, **ninguna de las 137 líneas** supera el umbral del 100% de carga. La línea más cargada de toda la red alcanza únicamente el **71.66 %**, lo que representa un margen operativo holgado de casi **28 puntos porcentuales** respecto al límite térmico.

---

### Interpretación técnica
Esto es completamente esperable en un escenario de demanda mínima: con menor consumo en el sistema, los flujos de potencia son más bajos y las líneas operan muy por debajo de su capacidad nominal. Si desea comparar con los escenarios **CR_Med** o **CR_Max**, donde la demanda es mayor y la probabilidad de sobrecarga aumenta, con gusto realizo el mismo análisis.
```


---

## CR_Med · Q1_resumen

**Consulta:** Carga la red CR_Med y reporta Vmin, Vmax (en pu) y la carga máxima de línea (en %). Indícame también cuántas barras tiene la red y cuántas tienen resultado válido.


**Iteraciones:** 2  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 15.0 s


**Usage:** in=5100, out=606, costo=$0.0244


**Tool calls:**

- `run_power_flow({'network': 'CR_Med'})`
  - resumen: `{'network': 'CR_Med', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7929589799405847, 'v_max_pu': 1.2489713022049864, 'max_line_loading_percent': 42.94918669247005, 'max_trafo_loading_percent': 88.63611259741957}`

**Respuesta final:**

```
¡Red cargada y flujo de potencia convergido! Aquí está el resumen de la red **CR_Med** (escenario de demanda media de Costa Rica):

---

## 📊 Resumen — Red CR_Med

| Parámetro | Valor |
|---|---|
| **Convergencia** | ✅ Sí (Newton-Raphson) |
| **Total de barras** | 524 |
| **Barras con resultado válido** | 513 |
| **Barras sin resultado** | 11 *(ver nota abajo)* |
| **Líneas** | 137 |
| **Transformadores** | 256 |

---

## ⚡ Perfil de Tensión

| Indicador | Valor (pu) |
|---|---|
| **V mínima** | 0.7930 pu |
| **V máxima** | 1.2490 pu |

---

## 🔌 Carga Máxima

| Elemento | Carga máxima |
|---|---|
| **Líneas** | 42.95 % |
| **Transformadores** | 88.64 % |

---

## 📝 Notas importantes

1. **Tensiones fuera del rango estándar (0.95–1.05 pu):** La red CR opera por diseño con perfiles de tensión que violan el rango convencional. Los valores de Vmin ≈ 0.79 pu y Vmax ≈ 1.25 pu son una característica reconocida del modelo, no un error numérico.

2. **11 barras sin resultado:** Corresponden a 3 unidades generadoras no despachadas en este escenario y 8 devanados terciarios de transformadores desactivados. Son excluidas automáticamente del análisis y **no representan un problema de convergencia**.

3. **Carga de líneas y transformadores saludable:** Ninguna línea supera el 43% de su capacidad, y el transformador más cargado llega al 88.6% — sin sobrecargas en este escenario.
```


---

## CR_Med · Q2_subtensiones

**Consulta:** En la red CR_Med, ¿cuántas barras presentan subtensión (< 0.95 pu)? Lista las 5 barras con menor tensión, indicando su índice de barra y el valor de tensión en pu.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 19.0 s


**Usage:** in=10222, out=889, costo=$0.0440


**Tool calls:**

- `run_power_flow({'network': 'CR_Med'})`
  - resumen: `{'network': 'CR_Med', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7929589799405847, 'v_max_pu': 1.2489713022049864, 'max_line_loading_percent': 42.94918669247005, 'max_trafo_loading_percent': 88.63611259741957}`
- `get_voltage_violations({'v_min': 0.95, 'v_max': 1.05, 'limit': 524})`
  - resumen: `{'network': 'CR_Med', 'v_min_threshold': 0.95, 'v_max_threshold': 1.05, 'n_violations_total': 58, 'n_subtension': 28, 'n_sobretension': 30, 'limit_applied': 524}`
  - violations[:3]: `[{'bus_index': 50280, 'vm_pu': 0.7929589799405847, 'tipo': 'subtension'}, {'bus_index': 58312, 'vm_pu': 0.8624702795633657, 'tipo': 'subtension'}, {'bus_index': 58234, 'vm_pu': 0.89257183366462, 'tipo': 'subtension'}]`

**Respuesta final:**

```
Aquí está el análisis completo para la red **CR_Med** en escenario de demanda media:

---

## 🔎 Resumen del Flujo de Potencia — CR_Med

| Parámetro | Valor |
|---|---|
| Convergencia | ✅ Sí |
| Barras totales | 524 (513 con resultado) |
| Tensión mínima global | 0.7930 pu |
| Tensión máxima global | 1.2490 pu |

> ⚠️ **Nota operativa:** La red CR opera con un perfil de tensiones que típicamente excede el rango estándar ±5% (0.95–1.05 pu) por diseño. Esto es una característica reconocida del modelo, no un error numérico.

---

## 📊 Violaciones de Subtensión (< 0.95 pu)

**Total de barras con subtensión: 28**

### 🔴 Las 5 barras con menor tensión:

| Ranking | Índice de Barra | Tensión (pu) | Desviación vs. 0.95 pu |
|---|---|---|---|
| 1° | **50280** | **0.7930 pu** | −16.53% |
| 2° | **58312** | **0.8625 pu** | −9.21% |
| 3° | **58234** | **0.8926 pu** | −6.04% |
| 4° | **53230** | **0.8961 pu** | −5.70% |
| 5° | **50830** | **0.8996 pu** | −5.30% |

---

## 📝 Conclusiones

- **28 de 513 barras** (≈ 5.5%) presentan subtensión por debajo de 0.95 pu.
- La barra **50280** es la más crítica, con apenas **0.7930 pu**, lo que representa una caída de casi **−16.5%** respecto al límite inferior estándar.
- Las barras **58312** y **58234** también son preocupantes, con tensiones en el rango 0.86–0.89 pu.
- Adicionalmente, existen **30 barras con sobretensión** (> 1.05 pu), lo que refleja el perfil operativo amplio característico de esta red.
```


---

## CR_Med · Q3_sobrecargas

**Consulta:** En la red CR_Med, ¿hay líneas sobrecargadas (carga > 100%)? Si las hay, dime cuántas son en total y lista hasta 5 con el índice de línea, las barras de extremo y el porcentaje de carga.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 13.5 s


**Usage:** in=8048, out=622, costo=$0.0335


**Tool calls:**

- `run_power_flow({'network': 'CR_Med'})`
  - resumen: `{'network': 'CR_Med', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7929589799405847, 'v_max_pu': 1.2489713022049864, 'max_line_loading_percent': 42.94918669247005, 'max_trafo_loading_percent': 88.63611259741957}`
- `get_overloaded_lines({'loading_threshold': 100, 'limit': 5})`
  - resumen: `{'network': 'CR_Med', 'loading_threshold_percent': 100, 'n_overloaded_total': 0, 'limit_applied': 5}`
  - overloaded[:3]: `[]`

**Respuesta final:**

```
## Resultado — Red CR_Med (Demanda Media)

**No hay ninguna línea sobrecargada** con carga superior al 100 % en el escenario de demanda media.

Aquí el resumen del estado de la red tras el flujo de potencia Newton-Raphson:

| Parámetro | Valor |
|---|---|
| Convergencia | ✅ Sí |
| N.º de barras | 524 (513 con resultado) |
| N.º de líneas | 137 |
| N.º de transformadores | 256 |
| **Carga máxima de líneas** | **42.95 %** |
| Carga máxima de transformadores | 88.64 % |
| V_min | 0.7930 pu |
| V_max | 1.2490 pu |

### Interpretación
- **Líneas sobrecargadas (> 100 %): 0 de 137.** La línea más exigida apenas llega al **42.95 %** de su capacidad, lo que indica un amplio margen térmico en todas las líneas del sistema.
- Los transformadores tampoco presentan sobrecarga, con un máximo de **88.64 %** (dentro del límite, aunque con menor margen que las líneas).
- Los perfiles de tensión (V entre 0.79 y 1.25 pu) se salen del rango estándar 0.95–1.05 pu, lo cual es una **característica reconocida del modelo CR** por diseño operativo, no un error numérico.
```


---

## CR_Max · Q1_resumen

**Consulta:** Carga la red CR_Max y reporta Vmin, Vmax (en pu) y la carga máxima de línea (en %). Indícame también cuántas barras tiene la red y cuántas tienen resultado válido.


**Iteraciones:** 2  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 11.2 s


**Usage:** in=5100, out=580, costo=$0.0240


**Tool calls:**

- `run_power_flow({'network': 'CR_Max'})`
  - resumen: `{'network': 'CR_Max', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7521406878277953, 'v_max_pu': 1.2473869569667584, 'max_line_loading_percent': 59.19619449797754, 'max_trafo_loading_percent': 88.72078183201276}`

**Respuesta final:**

```
¡Aquí está el resumen completo de la red **CR_Max** (escenario de demanda máxima de Costa Rica):

---

### ⚡ Resumen del Flujo de Potencia — CR_Max

| Parámetro | Valor |
|---|---|
| **Convergencia** | ✅ Sí (Newton-Raphson) |
| **Total de barras** | 524 |
| **Barras con resultado válido** | 513 |
| **Barras sin resultado** | 11 *(ver nota abajo)* |
| **Tensión mínima (Vmin)** | **0.7521 pu** |
| **Tensión máxima (Vmax)** | **1.2474 pu** |
| **Carga máxima de línea** | **59.20 %** |
| **Carga máxima de transformador** | **88.72 %** |

---

### 📝 Notas importantes

1. **Perfil de tensión fuera del rango estándar (0.95–1.05 pu):** El Vmin de 0.7521 pu y el Vmax de 1.2474 pu son característicos del modelo operativo de la red CR. Este comportamiento es una condición de diseño reconocida del modelo, no un error numérico. Las redes de transmisión reales de Costa Rica operan con rangos de tensión más amplios y compensación específica por zona.

2. **11 barras sin resultado:** Corresponden a **3 unidades generadoras no despachadas** en el escenario de demanda máxima y **8 devanados terciarios desactivados**. No representan un problema de convergencia.

3. **Líneas:** Ninguna línea supera el 100% de carga (máximo 59.20%), lo que indica que las líneas operan con margen holgado en este escenario. El elemento más exigido es un transformador al **88.72%**, aún dentro de límites operativos.
```


---

## CR_Max · Q2_subtensiones

**Consulta:** En la red CR_Max, ¿cuántas barras presentan subtensión (< 0.95 pu)? Lista las 5 barras con menor tensión, indicando su índice de barra y el valor de tensión en pu.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 21.4 s


**Usage:** in=9529, out=942, costo=$0.0427


**Tool calls:**

- `run_power_flow({'network': 'CR_Max'})`
  - resumen: `{'network': 'CR_Max', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7521406878277953, 'v_max_pu': 1.2473869569667584, 'max_line_loading_percent': 59.19619449797754, 'max_trafo_loading_percent': 88.72078183201276}`
- `get_voltage_violations({'v_min': 0.95, 'v_max': 1.05, 'limit': 524})`
  - resumen: `{'network': 'CR_Max', 'v_min_threshold': 0.95, 'v_max_threshold': 1.05, 'n_violations_total': 40, 'n_subtension': 29, 'n_sobretension': 11, 'limit_applied': 524}`
  - violations[:3]: `[{'bus_index': 50280, 'vm_pu': 0.7521406878277953, 'tipo': 'subtension'}, {'bus_index': 50830, 'vm_pu': 0.8640498234840718, 'tipo': 'subtension'}, {'bus_index': 54080, 'vm_pu': 0.8924889380983217, 'tipo': 'subtension'}]`

**Respuesta final:**

```
Tengo todos los datos necesarios. Aquí está el análisis completo:

---

## 🔌 Análisis de Subtensión — Red CR_Max (Demanda Máxima)

### Resumen del flujo de potencia
| Parámetro | Valor |
|---|---|
| Flujo convergido | ✅ Sí |
| Barras con resultado | 513 / 524 |
| V mínima global | **0.7521 pu** |
| V máxima global | **1.2474 pu** |

> ⚠️ **Nota operativa:** La red CR opera con perfiles de tensión que por diseño exceden el rango estándar (0.95–1.05 pu). Los rangos extremos observados (0.75–1.25 pu) son una condición reconocida del modelo, no un error numérico.

---

### 📊 Violaciones de tensión (< 0.95 pu)

**Total de barras con subtensión: 29 barras**
*(De un total de 40 violaciones: 29 subtensiones + 11 sobretensiones)*

---

### 🔴 Las 5 barras con menor tensión

| Posición | Índice de Barra | Tensión (pu) | Desviación respecto a 0.95 pu |
|:---:|:---:|:---:|:---:|
| 1° | **50280** | **0.7521 pu** | −0.1979 pu |
| 2° | **50830** | **0.8640 pu** | −0.0860 pu |
| 3° | **54080** | **0.8925 pu** | −0.0575 pu |
| 4° | **50831** | **0.8974 pu** | −0.0526 pu |
| 5° | **53080** | **0.9037 pu** | −0.0463 pu |

---

### 🔍 Observaciones clave
- La **barra 50280** es la más crítica con apenas **0.7521 pu**, una desviación de casi **−20%** respecto al límite inferior estándar.
- Las barras **50830, 54080 y 50831** también presentan tensiones severamente deprimidas (por debajo de 0.89–0.86 pu), lo que sugiere una zona de la red con deficiencia de soporte reactivo o alta demanda concentrada en el escenario de carga máxima.
- Se recomienda evaluar compensación reactiva o refuerzo de red en el entorno de estas barras para el escenario CR_Max.
```


---

## CR_Max · Q3_sobrecargas

**Consulta:** En la red CR_Max, ¿hay líneas sobrecargadas (carga > 100%)? Si las hay, dime cuántas son en total y lista hasta 5 con el índice de línea, las barras de extremo y el porcentaje de carga.


**Iteraciones:** 3  ·  **Stop reason:** `end_turn`  ·  **Tiempo:** 14.5 s


**Usage:** in=8070, out=685, costo=$0.0345


**Tool calls:**

- `run_power_flow({'network': 'CR_Max'})`
  - resumen: `{'network': 'CR_Max', 'converged': True, 'n_buses': 524, 'n_buses_with_result': 513, 'n_lines': 137, 'n_trafos': 256, 'v_min_pu': 0.7521406878277953, 'v_max_pu': 1.2473869569667584, 'max_line_loading_percent': 59.19619449797754, 'max_trafo_loading_percent': 88.72078183201276}`
- `get_overloaded_lines({'loading_threshold': 100, 'limit': 20})`
  - resumen: `{'network': 'CR_Max', 'loading_threshold_percent': 100, 'n_overloaded_total': 0, 'limit_applied': 20}`
  - overloaded[:3]: `[]`

**Respuesta final:**

```
Los resultados son claros. Aquí está el análisis completo:

---

## 🔍 Análisis de Sobrecargas — Red CR_Max (Demanda Máxima)

### ✅ No hay líneas sobrecargadas

El flujo de potencia **convergió correctamente** y la revisión exhaustiva de las **137 líneas** de la red no encontró ninguna con carga superior al **100%**.

| Parámetro | Valor |
|---|---|
| Red | CR_Max (524 barras, demanda máxima) |
| Convergencia | ✅ Sí |
| Total de líneas | 137 |
| Líneas sobrecargadas (> 100%) | **0** |
| **Carga máxima de línea** | **59.20 %** |
| Carga máxima de transformador | 88.72 % |

### 📌 Observaciones técnicas
- La línea más cargada apenas alcanza el **59.20 %** de su capacidad nominal, lo que indica un **margen de seguridad holgado** en las líneas de transmisión para el escenario de demanda máxima.
- Los **transformadores** presentan una carga mayor (hasta 88.72 %), aunque también por debajo del límite de sobrecarga. Este es el elemento con menor margen operativo en la red.
- Cabe señalar que el perfil de tensiones de la red CR opera fuera del rango estándar 0.95–1.05 pu por diseño del modelo (Vmin ≈ 0.7521 pu, Vmax ≈ 1.2474 pu), lo cual es una condición conocida del modelo y no afecta la validez del análisis de sobrecargas.
```
