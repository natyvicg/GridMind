"""
escenarios_ieee14.py
====================
Construcción de los 4 escenarios de prueba basados en IEEE 14
para validación del agente GridMind (TFG Natalia Víctor, Día 3).

Los 4 escenarios se dividen en dos grupos:

GRUPO A — Modelo oficial sin modificaciones
    0. ORIGINAL       — IEEE 14 tal como está en el CDF (AEP Test System, 1962).
                        Sirve para mostrar que el modelo oficial es referencia
                        matemática (validación de solvers), no operativa:
                        presenta 9 barras con V > 1.05 pu por diseño.

GRUPO B — Modelo calibrado a condiciones operativas
    Tres escenarios sobre una versión "calibrada" (setpoints a 1.02 pu y
    max_i_ka recalibrado), que representa la red bajo criterios de operación
    real (IEEE Std / ANSI C84.1: V ∈ [0.95, 1.05] pu, cargabilidad < 100%).

    1. BASE           — red calibrada sin violaciones (control negativo)
    2. SUBTENSIÓN     — barras con V < 0.95 pu (problema de control de tensión)
    3. SOBRECARGA     — líneas con cargabilidad > 100% (contingencia N-1)

Justificación de la calibración (aplica a BASE, SUBTENSIÓN, SOBRECARGA):
- Setpoints de gens normalizados a 1.02 pu (condiciones operativas típicas).
  Los setpoints originales (1.06-1.09) son para validar convergencia de
  solvers, no para evaluar criterios operativos modernos.
- Límites térmicos (max_i_ka) calibrados a 2x el flujo base → líneas al 50%
  en condiciones normales, criterio realista de planificación. Los 42.33 kA
  de fábrica producen cargabilidades de 1-2%, impidiendo escenarios de
  sobrecarga realistas.
"""
import pandapower as pp
import pandapower.networks as pn


# Umbrales operativos (criterio IEEE / operación normal)
V_MIN_OK = 0.95
V_MAX_OK = 1.05
CARGA_MAX_OK = 100.0  # %


def case14_ajustado():
    """
    Construye la red IEEE 14 con dos ajustes ingenieriles:

    1. Setpoints de generadores normalizados a 1.02 pu.
       Justificación: IEEE 14 de fábrica usa setpoints muy altos (1.06-1.09 pu)
       que causan sobretensión generalizada. Bajar a 1.02 pu representa una
       condición operativa normal y deja la red "limpia" como control negativo.

    2. Límites térmicos calibrados: max_i_ka = 2 × (flujo base en kA).
       Justificación: IEEE 14 trae max_i_ka = 42.3 kA en todas las líneas, 
       valor absurdamente sobredimensionado (cargabilidades base de 1-2%).
       Recalibrar a 2x el flujo natural deja cada línea al 50% en operación
       normal, que es criterio realista de planificación.

    Retorna: red pandapower con flujo convergido.
    """
    net = pn.case14()

    # Ajuste 1: setpoints normalizados
    net.gen['vm_pu'] = 1.02
    net.ext_grid['vm_pu'] = 1.02

    # Correr flujo con setpoints ajustados para obtener flujos base reales
    pp.runpp(net)

    # Ajuste 2: recalibrar max_i_ka a 2x el flujo base
    flujos_base_ka = net.line['max_i_ka'] * net.res_line['loading_percent'] / 100
    net.line['max_i_ka'] = (flujos_base_ka * 2).clip(lower=0.1)

    # Correr nuevamente con los nuevos límites (el flujo no cambia, solo la cargabilidad%)
    pp.runpp(net)
    return net


def escenario_0_original():
    """
    Escenario 0 — ORIGINAL (modelo oficial IEEE 14 sin modificaciones).

    Carga la red IEEE 14 tal como está definida en el archivo CDF del
    AEP Test System (1962, UW Archive 1993), sin ningún ajuste.

    Propósito en el TFG:
    - Mostrar explícitamente que se partió del modelo de referencia oficial.
    - Demostrar que el modelo oficial no cumple criterios operativos modernos
      (ANSI C84.1 / IEEE Std): presenta sobretensiones generalizadas.
    - Servir como examen adicional del agente: debe identificar 9 barras
      con sobretensión simultánea (caso de mayor complejidad).

    Diferencia clave con los otros 3 escenarios:
    - Setpoints de gens SIN normalizar (valores oficiales 1.06, 1.045,
      1.01, 1.07, 1.09 pu).
    - max_i_ka SIN recalibrar (valor oficial 42.33 kA → cargabilidades de 1-2%).

    Violaciones esperadas (ground truth):
    - 9 barras con V > 1.05 pu: B1, B6, B7, B8, B9, B10, B11, B12, B13
      (Vmax = 1.090 pu en bus 8)
    - 0 barras con V < 0.95 pu
    - 0 líneas con cargabilidad > 100% (cargabilidad máx. ≈ 1.5%)
    """
    net = pn.case14()
    pp.runpp(net)
    return net


def escenario_1_base():
    """
    Escenario 1 — BASE CALIBRADO (control negativo).

    Red IEEE 14 calibrada a condiciones operativas (ver case14_ajustado),
    sin modificaciones adicionales. Representa la red "sana" bajo criterios
    de operación normal.

    Propósito: control negativo. El agente NO debe reportar ninguna violación.
    Permite detectar falsos positivos (problema clásico de LLMs que inventan
    violaciones donde no las hay).

    Violaciones esperadas: NINGUNA.
    """
    net = case14_ajustado()
    return net


def escenario_2_subtension():
    """
    Escenario 2 — SUBTENSIÓN.

    Modificación: reducir setpoint de generadores PV en buses 6 y 8 a 0.95 pu.
    Simula un problema de control de tensión (regulador del generador limitado
    o falla parcial de compensación reactiva) en la zona sur de la red.

    Violaciones esperadas:
    - 5 barras con V < 0.95 pu: buses 10, 11, 12, 13, 14
    - Vmin ≈ 0.924 pu en bus 14 (barra más alejada del slack)
    - Ninguna sobrecarga (cargabilidad máxima ≈ 75%)
    """
    net = case14_ajustado()
    net.gen.loc[net.gen.bus.isin([5, 7]), 'vm_pu'] = 0.95  # buses 6 y 8 (0-indexed: 5,7)
    pp.runpp(net)
    return net


def escenario_3_sobrecarga():
    """
    Escenario 3 — SOBRECARGA.

    Modificación combinada:
    - Contingencia N-1: desconectar línea entre buses 1 y 5 (línea índice 1).
    - Escalado de cargas a 1.3x el valor base.

    Justificación: simula pérdida de una línea de transmisión durante un
    período de demanda elevada. Es el escenario clásico de planificación N-1.

    Violaciones esperadas:
    - 2 líneas con cargabilidad > 100%:
        · Línea 1-2: ≈ 105%
        · Línea 2-5: ≈ 122%
    - Ninguna violación de tensión (Vmin ≈ 0.964 pu, dentro de rango)
    """
    net = case14_ajustado()
    # Desconectar línea 1-5 (from_bus=0, to_bus=4 en 0-indexed)
    linea_desc = net.line[(net.line.from_bus == 0) & (net.line.to_bus == 4)].index
    net.line.loc[linea_desc, 'in_service'] = False
    # Escalar cargas
    net.load['p_mw'] *= 1.3
    net.load['q_mvar'] *= 1.3
    pp.runpp(net)
    return net


def construir_escenarios():
    """
    Construye los 4 escenarios y los devuelve en un dict ordenado.

    El orden de iteración es: original, base, subtension, sobrecarga.

    Retorna: dict {nombre: net} con los 4 escenarios.
    """
    return {
        'original': escenario_0_original(),
        'base': escenario_1_base(),
        'subtension': escenario_2_subtension(),
        'sobrecarga': escenario_3_sobrecarga(),
    }


def detectar_violaciones(net):
    """
    Detecta y cuantifica las violaciones operativas en una red.

    Retorna: dict con
        - barras_subtension: DataFrame de barras con V < V_MIN_OK
        - barras_sobretension: DataFrame de barras con V > V_MAX_OK
        - lineas_sobrecarga: DataFrame de líneas con cargabilidad > CARGA_MAX_OK
        - vmin, vmax, loading_max: valores extremos
    """
    v = net.res_bus.vm_pu
    l = net.res_line.loading_percent

    return {
        'barras_subtension': net.res_bus[v < V_MIN_OK],
        'barras_sobretension': net.res_bus[v > V_MAX_OK],
        'lineas_sobrecarga': net.res_line[l > CARGA_MAX_OK],
        'vmin': v.min(),
        'vmax': v.max(),
        'bus_vmin': v.idxmin() + 1,   # +1 para numeración 1-based (convención ingenieril)
        'bus_vmax': v.idxmax() + 1,
        'loading_max': l.max(),
    }


# ============================================================
# Prueba rápida cuando se ejecuta el archivo directamente
# ============================================================
if __name__ == "__main__":
    escenarios = construir_escenarios()
    print("=" * 65)
    print("VALIDACIÓN RÁPIDA DE LOS 3 ESCENARIOS")
    print("=" * 65)
    for nombre, net in escenarios.items():
        v = detectar_violaciones(net)
        print(f"\n[{nombre.upper()}]")
        print(f"  Vmin = {v['vmin']:.4f} pu (bus {v['bus_vmin']})")
        print(f"  Vmax = {v['vmax']:.4f} pu (bus {v['bus_vmax']})")
        print(f"  Cargabilidad máxima = {v['loading_max']:.2f}%")
        print(f"  Barras subtensión: {len(v['barras_subtension'])}")
        print(f"  Barras sobretensión: {len(v['barras_sobretension'])}")
        print(f"  Líneas sobrecarga: {len(v['lineas_sobrecarga'])}")