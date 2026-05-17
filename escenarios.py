"""
escenarios.py — Escenarios de validación de GridMind (genérico + curados)
=========================================================================

SECCIÓN 1 — Escenarios genéricos
    construir_escenarios_red(network_key)
        Genera los 4 escenarios estándar (ORIGINAL, BASE, SUBTENSIÓN,
        SOBRECARGA) para CUALQUIER red IEEE del catálogo de tools.py.
        El ground truth se calcula automáticamente desde PandaPower.
        Cada escenario incluye un campo 'viable' que indica si realmente
        produjo el tipo de violación esperada.

    construir_todos_ieee()
        Ejecuta construir_escenarios_red() para todas las redes IEEE del
        catálogo y devuelve un dict consolidado.

SECCIÓN 2 — Escenarios curados (E1-E7)
    Los 7 escenarios originales con parámetros diseñados a mano para
    IEEE 14 (E1-E4) y Costa Rica (E5-E7). Se mantienen intactos para
    el TFG.

Heurísticas genéricas (SUBTENSIÓN y SOBRECARGA):
    - SUBTENSIÓN: se bajan a 0.95 pu los últimos ceil(n/2) generadores PV
      ordenados por índice de bus (determinista). Si no hay generadores PV
      (solo ext_grid), el escenario se marca como no viable.
    - SOBRECARGA: se desconecta la línea con mayor cargabilidad base
      (desempate: menor índice) y se escalan cargas ×1.3. Si no produce
      sobrecargas >100%, se marca como no viable.
    - Ambas heurísticas usan desempate por índice menor para garantizar
      reproducibilidad entre versiones de pandas/PandaPower.
"""

import os
import math
import copy
import pandas as pd
import pandapower as pp
import pandapower.networks as pn
from pathlib import Path


# ═════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═════════════════════════════════════════════════════════════════════════

GRIDMIND_DIR = Path(__file__).resolve().parent
RED_CR_SCRIPT = GRIDMIND_DIR / 'red_cr.py'
EXCEL_DIR = GRIDMIND_DIR

# Umbrales operativos estándar
V_MIN = 0.95
V_MAX = 1.05
LOADING_MAX = 100.0  # %

# Parámetros de calibración
SETPOINT_CALIBRADO = 1.02   # pu
FACTOR_MAX_I_KA = 2.0       # max_i_ka = factor × flujo base
MIN_MAX_I_KA = 0.1          # kA, piso para evitar divisiones por cero
SETPOINT_SUBTENSION = 0.95  # pu, setpoint reducido para inducir subtensión
FACTOR_CARGA = 1.3          # multiplicador de cargas para sobrecarga

# Barras aisladas conocidas de la red CR (despacho operativo)
BARRAS_AISLADAS_CR = [50066, 50081, 50383, 50384, 50582,
                      50930, 53130, 54881, 56082, 58324, 58326]


# ═════════════════════════════════════════════════════════════════════════
# CATÁLOGO IEEE (espejo de tools.py para no crear dependencia circular)
# ═════════════════════════════════════════════════════════════════════════

_IEEE_CATALOG = {
    "IEEE_4":        "case4gs",
    "IEEE_5":        "case5",
    "IEEE_6":        "case6ww",
    "IEEE_9":        "case9",
    "IEEE_14":       "case14",
    "IEEE_24_RTS":   "case24_ieee_rts",
    "IEEE_30":       "case30",
    "IEEE_33_BW":    "case33bw",
    "IEEE_39":       "case39",
    "IEEE_57":       "case57",
    "IEEE_89_PEGASE":"case89pegase",
    "IEEE_118":      "case118",
    "IEEE_145":      "case145",
    "IEEE_200":      "case_illinois200",
    "IEEE_300":      "case300",
}


# ═════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — FUNCIONES GENÉRICAS
# ═════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cargar_red_ieee(network_key):
    """Carga una red IEEE de fábrica desde pandapower.networks."""
    if network_key not in _IEEE_CATALOG:
        raise ValueError(
            f"Red '{network_key}' no está en el catálogo IEEE. "
            f"Opciones: {list(_IEEE_CATALOG.keys())}"
        )
    func = getattr(pn, _IEEE_CATALOG[network_key], None)
    if func is None:
        raise ValueError(
            f"Función pn.{_IEEE_CATALOG[network_key]}() no existe. "
            f"Verifique la versión de PandaPower."
        )
    return func()


def _calibrar_red(net):
    """
    Calibración genérica aplicable a cualquier red:
      1. Setpoints de todos los generadores y ext_grid → SETPOINT_CALIBRADO pu
      2. max_i_ka de todas las líneas → FACTOR_MAX_I_KA × flujo base

    Retorna la red calibrada con flujo de potencia ejecutado.
    No modifica la red in-place (trabaja sobre el objeto recibido).
    """
    if not net.gen.empty:
        net.gen.loc[:, 'vm_pu'] = SETPOINT_CALIBRADO
    net.ext_grid.loc[:, 'vm_pu'] = SETPOINT_CALIBRADO

    pp.runpp(net)

    # Recalibrar límites térmicos basados en flujo real
    for i in net.line.index:
        i_base = float(net.res_line.loc[i, 'i_ka'])
        net.line.loc[i, 'max_i_ka'] = max(i_base * FACTOR_MAX_I_KA, MIN_MAX_I_KA)

    # Re-ejecutar con nuevos límites (flujo no cambia, cargabilidad sí)
    pp.runpp(net)
    return net


def _calcular_ground_truth(net):
    """
    Calcula ground truth completo a partir de resultados de PandaPower.
    Devuelve dict con conteos, listas de índices y valores extremos.
    """
    vm = net.res_bus['vm_pu'].dropna()

    sub = vm[vm < V_MIN].sort_values()
    sobre_v = vm[vm > V_MAX].sort_values(ascending=False)

    gt = {
        'converged': bool(getattr(net, 'converged', True)),
        'n_buses': int(len(net.bus)),
        'n_buses_con_resultado': int(len(vm)),
        'v_min_pu': round(float(vm.min()), 5) if len(vm) else None,
        'v_max_pu': round(float(vm.max()), 5) if len(vm) else None,
        'n_subtension': int(len(sub)),
        'buses_subtension': [int(b) for b in sub.index],
        'n_sobretension': int(len(sobre_v)),
        'buses_sobretension': [int(b) for b in sobre_v.index],
    }

    # Líneas
    if not net.res_line.empty:
        loading_l = net.res_line['loading_percent'].dropna()
        over_l = loading_l[loading_l > LOADING_MAX].sort_values(ascending=False)
        gt['max_loading_linea_pct'] = round(float(loading_l.max()), 2) if len(loading_l) else None
        gt['n_lineas_sobrecarga'] = int(len(over_l))
        gt['lineas_sobrecarga'] = [int(i) for i in over_l.index]
    else:
        gt['max_loading_linea_pct'] = None
        gt['n_lineas_sobrecarga'] = 0
        gt['lineas_sobrecarga'] = []

    # Trafos 2W
    if not net.res_trafo.empty:
        loading_t = net.res_trafo['loading_percent'].dropna()
        over_t = loading_t[loading_t > LOADING_MAX].sort_values(ascending=False)
        gt['max_loading_trafo_pct'] = round(float(loading_t.max()), 2) if len(loading_t) else None
        gt['n_trafos_sobrecarga'] = int(len(over_t))
        gt['trafos_sobrecarga'] = [int(i) for i in over_t.index]
    else:
        gt['max_loading_trafo_pct'] = None
        gt['n_trafos_sobrecarga'] = 0
        gt['trafos_sobrecarga'] = []

    return gt


def _seleccionar_gens_subtension(net):
    """
    Selecciona generadores PV para inducir subtensión.

    Heurística: tomar la mitad superior de los generadores PV (ordenados
    por bus index ascendente). "Mitad superior" = los que tienen bus index
    más alto, que típicamente están más lejos del slack.

    Desempate: por índice de bus (determinista).

    Retorna: lista de índices en net.gen a modificar, o [] si no hay PV gens.
    """
    if net.gen.empty:
        return []

    # Buses del slack (ext_grid) — los excluimos
    slack_buses = set(net.ext_grid['bus'].astype(int).tolist())

    # Generadores PV (no slack), ordenados por bus index
    pv_mask = ~net.gen['bus'].isin(slack_buses) & net.gen['in_service']
    pv_gens = net.gen[pv_mask].sort_values('bus')

    if pv_gens.empty:
        return []

    # Tomar la mitad con bus index más alto (ceil para impar)
    n_total = len(pv_gens)
    n_bajar = math.ceil(n_total / 2)
    seleccionados = pv_gens.tail(n_bajar)

    return seleccionados.index.tolist()


def _seleccionar_linea_sobrecarga(net):
    """
    Selecciona la línea a desconectar para inducir sobrecarga.

    Heurística mejorada:
      1. Excluir líneas directamente conectadas al bus del ext_grid (slack),
         porque desconectarlas frecuentemente aísla la fuente principal y
         el flujo no converge.
      2. Usar flujo absoluto (i_ka) en vez de loading_percent. Después de
         la calibración (max_i_ka = 2×base), todas las líneas quedan al 50%
         de cargabilidad, haciendo loading_percent inútil para diferenciar.
         El flujo absoluto refleja la importancia real de la línea.
      3. Desempate: menor índice de línea (determinista).

    Retorna: índice de línea en net.line, o None si no hay candidatas.
    """
    if net.res_line.empty:
        return None

    # Buses del slack
    slack_buses = set(net.ext_grid['bus'].astype(int).tolist())

    # Filtrar: activas y NO conectadas al slack
    activas = net.line[net.line['in_service']].index
    candidatas_mask = (
        net.line.loc[activas, 'in_service'] &
        ~net.line.loc[activas, 'from_bus'].isin(slack_buses) &
        ~net.line.loc[activas, 'to_bus'].isin(slack_buses)
    )
    candidatas_idx = candidatas_mask[candidatas_mask].index

    # Si todas las líneas tocan el slack (red estrella), usar todas activas
    if candidatas_idx.empty:
        candidatas_idx = activas

    # Usar flujo absoluto para ranking
    i_ka = net.res_line.loc[candidatas_idx, 'i_ka'].dropna()
    if i_ka.empty:
        return None

    # Desempate determinista: entre las de i_ka máximo, tomar menor índice
    max_ika = i_ka.max()
    empatadas = i_ka[i_ka == max_ika]
    return int(empatadas.index.min())


# ---------------------------------------------------------------------------
# Constructores genéricos de escenarios
# ---------------------------------------------------------------------------

def _escenario_original(network_key):
    """
    Escenario ORIGINAL — red de fábrica sin modificaciones.
    Propósito: referencia del modelo oficial.
    """
    net = _cargar_red_ieee(network_key)

    try:
        pp.runpp(net)
        converged = True
    except Exception as e:
        return net, {
            'tipo': 'ORIGINAL',
            'network': network_key,
            'converged': False,
            'error': str(e),
            'viable': False,
            'razon': f'Flujo de fábrica no convergió: {e}',
        }, None

    gt = _calcular_ground_truth(net)

    meta = {
        'tipo': 'ORIGINAL',
        'network': network_key,
        'modelo': 'Oficial (fábrica PandaPower)',
        'proposito': 'Modelo de referencia sin modificaciones',
        'condicion_inicial': (
            f'{network_key} de fábrica — setpoints y max_i_ka originales'
        ),
        'converged': True,
        'viable': True,
        'razon': 'Modelo oficial siempre es viable como referencia',
    }

    return net, meta, gt


def _escenario_base(network_key):
    """
    Escenario BASE — red calibrada, control negativo.
    Propósito: validar que el agente no alucina violaciones.
    """
    net = _cargar_red_ieee(network_key)

    try:
        net = _calibrar_red(net)
    except Exception as e:
        return net, {
            'tipo': 'BASE',
            'network': network_key,
            'converged': False,
            'error': str(e),
            'viable': False,
            'razon': f'Calibración falló: {e}',
        }, None

    gt = _calcular_ground_truth(net)

    # El BASE es "limpio" si no tiene violaciones estrictas
    n_violaciones = gt['n_subtension'] + gt['n_sobretension'] + gt['n_lineas_sobrecarga']
    es_limpio = (n_violaciones == 0)

    meta = {
        'tipo': 'BASE',
        'network': network_key,
        'modelo': 'Calibrado',
        'proposito': 'Control negativo — validar ausencia de falsos positivos',
        'condicion_inicial': (
            f'Gens/ext_grid en {SETPOINT_CALIBRADO} pu, '
            f'max_i_ka = {FACTOR_MAX_I_KA}× flujo base'
        ),
        'converged': True,
        'viable': True,  # El BASE siempre es viable (incluso si tiene violaciones residuales)
        'control_negativo_limpio': es_limpio,
        'razon': (
            'Sin violaciones — control negativo perfecto' if es_limpio
            else (f'Nota: {n_violaciones} violaciones residuales tras calibración. '
                  f'El agente debe reportarlas correctamente.')
        ),
    }

    return net, meta, gt


def _escenario_subtension(network_key):
    """
    Escenario SUBTENSIÓN — generadores PV con setpoint reducido.
    Propósito: diagnóstico de violaciones de tensión baja.
    """
    net = _cargar_red_ieee(network_key)

    try:
        net = _calibrar_red(net)
    except Exception as e:
        return net, {
            'tipo': 'SUBTENSIÓN',
            'network': network_key,
            'converged': False,
            'error': str(e),
            'viable': False,
            'razon': f'Calibración base falló: {e}',
        }, None

    # Seleccionar generadores y aplicar reducción
    gens_a_bajar = _seleccionar_gens_subtension(net)

    if not gens_a_bajar:
        gt = _calcular_ground_truth(net)
        return net, {
            'tipo': 'SUBTENSIÓN',
            'network': network_key,
            'converged': True,
            'viable': False,
            'razon': 'No hay generadores PV (solo ext_grid) — no se puede inducir subtensión por setpoint',
            'gens_modificados': [],
        }, gt

    # Aplicar reducción de setpoint
    buses_afectados = []
    for idx in gens_a_bajar:
        buses_afectados.append(int(net.gen.at[idx, 'bus']))
        net.gen.at[idx, 'vm_pu'] = SETPOINT_SUBTENSION

    try:
        pp.runpp(net)
    except Exception as e:
        return net, {
            'tipo': 'SUBTENSIÓN',
            'network': network_key,
            'converged': False,
            'error': str(e),
            'viable': False,
            'razon': f'Flujo no convergió tras reducir setpoints: {e}',
            'gens_modificados': gens_a_bajar,
            'buses_afectados': buses_afectados,
        }, None

    gt = _calcular_ground_truth(net)
    tiene_subtension = gt['n_subtension'] > 0

    meta = {
        'tipo': 'SUBTENSIÓN',
        'network': network_key,
        'modelo': 'Calibrado + setpoints reducidos',
        'proposito': 'Diagnóstico de violaciones de tensión baja',
        'condicion_inicial': (
            f'Sobre red calibrada — setpoint de {len(gens_a_bajar)} generadores PV '
            f'(buses {buses_afectados}) bajado a {SETPOINT_SUBTENSION} pu'
        ),
        'converged': True,
        'viable': tiene_subtension,
        'gens_modificados': gens_a_bajar,
        'buses_afectados': buses_afectados,
        'razon': (
            f'{gt["n_subtension"]} barras con V < {V_MIN} pu' if tiene_subtension
            else (f'Reducir setpoints a {SETPOINT_SUBTENSION} pu no indujo subtensión. '
                  f'La red tiene suficiente soporte reactivo para compensar.')
        ),
    }

    return net, meta, gt


def _escenario_sobrecarga(network_key):
    """
    Escenario SOBRECARGA — contingencia N-1 + escalado de cargas.
    Propósito: diagnóstico térmico / análisis de contingencia.
    """
    net = _cargar_red_ieee(network_key)

    try:
        net = _calibrar_red(net)
    except Exception as e:
        return net, {
            'tipo': 'SOBRECARGA',
            'network': network_key,
            'converged': False,
            'error': str(e),
            'viable': False,
            'razon': f'Calibración base falló: {e}',
        }, None

    # Seleccionar línea a desconectar
    linea_desc = _seleccionar_linea_sobrecarga(net)

    if linea_desc is None:
        gt = _calcular_ground_truth(net)
        return net, {
            'tipo': 'SOBRECARGA',
            'network': network_key,
            'converged': True,
            'viable': False,
            'razon': 'No hay líneas activas con resultado — no se puede simular N-1',
            'linea_desconectada': None,
        }, gt

    # Registrar datos de la línea antes de desconectar
    from_bus = int(net.line.at[linea_desc, 'from_bus'])
    to_bus = int(net.line.at[linea_desc, 'to_bus'])
    loading_pre = round(float(net.res_line.at[linea_desc, 'loading_percent']), 2)

    # Desconectar línea
    net.line.at[linea_desc, 'in_service'] = False

    # Escalar cargas
    if not net.load.empty:
        net.load.loc[:, 'p_mw'] = net.load['p_mw'] * FACTOR_CARGA
        net.load.loc[:, 'q_mvar'] = net.load['q_mvar'] * FACTOR_CARGA

    try:
        pp.runpp(net)
    except pp.LoadflowNotConverged as e:
        return net, {
            'tipo': 'SOBRECARGA',
            'network': network_key,
            'converged': False,
            'viable': False,
            'razon': (
                f'Flujo no convergió tras desconectar línea {linea_desc} '
                f'(bus {from_bus}→{to_bus}) + cargas ×{FACTOR_CARGA}. '
                f'La red no tiene redundancia suficiente.'
            ),
            'linea_desconectada': linea_desc,
            'linea_from_bus': from_bus,
            'linea_to_bus': to_bus,
            'linea_loading_pre': loading_pre,
            'error': str(e),
        }, None
    except Exception as e:
        return net, {
            'tipo': 'SOBRECARGA',
            'network': network_key,
            'converged': False,
            'viable': False,
            'razon': f'Error inesperado: {e}',
            'linea_desconectada': linea_desc,
            'error': str(e),
        }, None

    gt = _calcular_ground_truth(net)
    tiene_sobrecarga = gt['n_lineas_sobrecarga'] > 0 or gt.get('n_trafos_sobrecarga', 0) > 0

    meta = {
        'tipo': 'SOBRECARGA',
        'network': network_key,
        'modelo': 'Calibrado + N-1 + cargas escaladas',
        'proposito': 'Diagnóstico térmico + análisis de contingencia N-1',
        'condicion_inicial': (
            f'Sobre red calibrada — línea idx={linea_desc} (bus {from_bus}→{to_bus}, '
            f'loading base {loading_pre}%) desconectada + cargas ×{FACTOR_CARGA}'
        ),
        'converged': True,
        'viable': tiene_sobrecarga,
        'linea_desconectada': linea_desc,
        'linea_from_bus': from_bus,
        'linea_to_bus': to_bus,
        'linea_loading_pre': loading_pre,
        'razon': (
            f'{gt["n_lineas_sobrecarga"]} líneas + {gt.get("n_trafos_sobrecarga", 0)} '
            f'trafos con cargabilidad > {LOADING_MAX}%' if tiene_sobrecarga
            else (f'N-1 + cargas ×{FACTOR_CARGA} no indujo sobrecargas. '
                  f'La red tiene holgura térmica suficiente.')
        ),
    }

    return net, meta, gt


# ---------------------------------------------------------------------------
# Función principal genérica
# ---------------------------------------------------------------------------

def construir_escenarios_red(network_key):
    """
    Construye los 4 escenarios estándar para cualquier red IEEE del catálogo.

    Parámetros:
        network_key: str — clave del catálogo (ej. "IEEE_14", "IEEE_118")

    Retorna: dict con 4 entradas, cada una con:
        'net':   red pandapower con PF ejecutado
        'meta':  dict con metadata (tipo, propósito, viable, razón, etc.)
        'gt':    dict con ground truth (None si no convergió)

    Ejemplo:
        resultados = construir_escenarios_red("IEEE_30")
        for nombre, data in resultados.items():
            print(f"{nombre}: viable={data['meta']['viable']}")
    """
    builders = {
        'ORIGINAL':    _escenario_original,
        'BASE':        _escenario_base,
        'SUBTENSIÓN':  _escenario_subtension,
        'SOBRECARGA':  _escenario_sobrecarga,
    }

    resultados = {}
    for nombre, builder in builders.items():
        net, meta, gt = builder(network_key)
        resultados[nombre] = {
            'net': net,
            'meta': meta,
            'gt': gt,
        }

    return resultados


def construir_todos_ieee():
    """
    Ejecuta los 4 escenarios para TODAS las redes IEEE del catálogo.

    Retorna: dict {network_key: {escenario: {net, meta, gt}}}

    Útil para generar la tabla consolidada de viabilidad por red.
    """
    todos = {}
    for key in _IEEE_CATALOG:
        print(f"  Procesando {key}...")
        try:
            todos[key] = construir_escenarios_red(key)
        except Exception as e:
            print(f"    ✗ Error en {key}: {e}")
            todos[key] = {'error': str(e)}
    return todos


def resumen_viabilidad(todos):
    """
    Genera un DataFrame resumen de viabilidad para todas las redes.

    Parámetros:
        todos: dict retornado por construir_todos_ieee()

    Retorna: pd.DataFrame con una fila por red y columnas de viabilidad
             por escenario + resumen del ground truth.
    """
    filas = []
    for network_key, escenarios in todos.items():
        if 'error' in escenarios:
            filas.append({
                'Red': network_key,
                'N barras': '—',
                'ORIGINAL': '✗ error',
                'BASE': '✗ error',
                'SUBTENSIÓN': '✗ error',
                'SOBRECARGA': '✗ error',
                'Nota': escenarios['error'],
            })
            continue

        fila = {'Red': network_key}

        for tipo in ['ORIGINAL', 'BASE', 'SUBTENSIÓN', 'SOBRECARGA']:
            data = escenarios[tipo]
            meta = data['meta']
            gt = data['gt']

            if not meta.get('converged', False):
                fila[tipo] = '✗ no converge'
            elif not meta.get('viable', False):
                fila[tipo] = f'— no viable'
            else:
                # Resumen compacto del GT
                if tipo == 'ORIGINAL':
                    nv = gt['n_sobretension'] + gt['n_subtension']
                    fila[tipo] = f'✓ {nv} viol.V'
                    fila['N barras'] = gt['n_buses']
                elif tipo == 'BASE':
                    limpio = meta.get('control_negativo_limpio', False)
                    fila[tipo] = '✓ limpio' if limpio else f'✓ {gt["n_subtension"]+gt["n_sobretension"]} residuales'
                elif tipo == 'SUBTENSIÓN':
                    fila[tipo] = f'✓ {gt["n_subtension"]} sub'
                elif tipo == 'SOBRECARGA':
                    nl = gt['n_lineas_sobrecarga']
                    nt = gt.get('n_trafos_sobrecarga', 0)
                    fila[tipo] = f'✓ {nl}L+{nt}T'

            fila.setdefault('Nota', meta.get('razon', ''))

        filas.append(fila)

    df = pd.DataFrame(filas)
    col_order = ['Red', 'N barras', 'ORIGINAL', 'BASE', 'SUBTENSIÓN', 'SOBRECARGA', 'Nota']
    return df[[c for c in col_order if c in df.columns]]


# ═════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — ESCENARIOS CURADOS (E1–E7)
# ═════════════════════════════════════════════════════════════════════════
# Estos son los escenarios diseñados a mano para el TFG, con parámetros
# específicos y narrativa ingenieril. Se mantienen intactos.

def _build_ieee14_base():
    """IEEE 14 con setpoint de gens a 1.02 pu y max_i_ka recalibrado a 2×base."""
    net = pp.networks.case14()
    net.gen.loc[:, 'vm_pu'] = SETPOINT_CALIBRADO
    net.ext_grid.loc[:, 'vm_pu'] = SETPOINT_CALIBRADO
    pp.runpp(net)
    for i in net.line.index:
        i_base = float(net.res_line.loc[i, 'i_ka'])
        net.line.loc[i, 'max_i_ka'] = max(i_base * FACTOR_MAX_I_KA, MIN_MAX_I_KA)
    return net


def build_E1_IEEE14_ORIGINAL():
    """Modelo CDF oficial sin calibrar — setpoints 1.06-1.09 pu, max_i_ka original."""
    net = pp.networks.case14()
    pp.runpp(net)
    meta = {
        'id': 'E1', 'red': 'IEEE 14', 'nombre': 'ORIGINAL',
        'modelo': 'Oficial',
        'proposito': 'Modelo de referencia matemática (AEP Test System 1962) — 9 barras con sobretensión por diseño',
        'condicion_inicial': 'IEEE 14 sin modificaciones (setpoints oficiales 1.06-1.09 pu, max_i_ka = 42.33 kA)',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus[net.bus.in_service]),
        'n1_elemento': 'line idx=0 (bus 0 → bus 1)',
    }
    return net, meta


def build_E2_IEEE14_BASE():
    net = _build_ieee14_base()
    pp.runpp(net)
    meta = {
        'id': 'E2', 'red': 'IEEE 14', 'nombre': 'BASE',
        'modelo': 'Calibrado',
        'proposito': 'Control negativo — validar que el agente no alucina violaciones',
        'condicion_inicial': f'Red calibrada, gens y ext_grid en {SETPOINT_CALIBRADO} pu, max_i_ka = {FACTOR_MAX_I_KA}×flujo base',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus[net.bus.in_service]),
        'n1_elemento': 'line idx=0 (bus 0 → bus 1)',
    }
    return net, meta


def build_E3_IEEE14_SUBTENSION():
    net = _build_ieee14_base()
    for idx in net.gen.index:
        bus = int(net.gen.loc[idx, 'bus'])
        if bus in [5, 7]:
            net.gen.loc[idx, 'vm_pu'] = SETPOINT_SUBTENSION
    pp.runpp(net)
    meta = {
        'id': 'E3', 'red': 'IEEE 14', 'nombre': 'SUBTENSIÓN',
        'modelo': 'Calibrado',
        'proposito': 'Diagnóstico de tensión',
        'condicion_inicial': f'Sobre red calibrada — setpoint gens buses 6 y 8 (idx 5, 7) bajado a {SETPOINT_SUBTENSION} pu',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus[net.bus.in_service]),
        'n1_elemento': 'line idx=1 (bus 0 → bus 4)',
    }
    return net, meta


def build_E4_IEEE14_SOBRECARGA():
    net = _build_ieee14_base()
    mask = ((net.line.from_bus == 0) & (net.line.to_bus == 4)) | \
           ((net.line.from_bus == 4) & (net.line.to_bus == 0))
    net.line.loc[mask, 'in_service'] = False
    net.load.loc[:, 'p_mw'] = net.load.p_mw * FACTOR_CARGA
    net.load.loc[:, 'q_mvar'] = net.load.q_mvar * FACTOR_CARGA
    pp.runpp(net)
    meta = {
        'id': 'E4', 'red': 'IEEE 14', 'nombre': 'SOBRECARGA',
        'modelo': 'Calibrado',
        'proposito': 'Diagnóstico térmico + análisis N-1',
        'condicion_inicial': f'Sobre red calibrada — línea 1-5 fuera de servicio + cargas × {FACTOR_CARGA}',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus[net.bus.in_service]),
        'n1_elemento': 'line más cargada remanente',
    }
    return net, meta


# ─── Costa Rica ──────────────────────────────────────────────────────────

def _detectar_nombre_excel(escenario):
    """Detecta si los xlsx están con o sin guión en la fecha."""
    candidatos = [
        f'Base_CR_{escenario}_2023Marzo.xlsx',
        f'Base_CR_{escenario}_2023-Marzo.xlsx',
    ]
    for nombre in candidatos:
        if (EXCEL_DIR / nombre).exists():
            return nombre
    raise FileNotFoundError(
        f"No encontré el archivo de {escenario} en {EXCEL_DIR}. "
        f"Esperaba alguno de: {candidatos}"
    )


def _build_cr(escenario):
    """Construye la red de CR para un escenario Min/Med/Max."""
    if not RED_CR_SCRIPT.exists():
        raise FileNotFoundError(
            f"No encontré red_cr.py en {RED_CR_SCRIPT}. "
            f"Ajustá la variable RED_CR_SCRIPT al inicio de escenarios.py."
        )

    nombre_xlsx = _detectar_nombre_excel(escenario)

    code = RED_CR_SCRIPT.read_text(encoding='utf-8')
    lineas = code.split('\n')
    nuevas = []
    for ln in lineas:
        ln_match = ('Base_CR_Min_2023' in ln or 'Base_CR_Med_2023' in ln
                    or 'Base_CR_Max_2023' in ln)
        if not ln_match:
            nuevas.append(ln)
            continue
        if f'Base_CR_{escenario}_2023' in ln:
            nuevas.append(
                f"base_datos = pd.read_excel('{nombre_xlsx}',"
                f"sheet_name=None,header=None)"
            )
        else:
            nuevas.append('#' + ln)

    script = '\n'.join(nuevas)
    marcador = "pp.runpp(Red_CR1, algorithm='nr')"
    idx = script.find(marcador)
    if idx < 0:
        raise RuntimeError(
            f"No encontré '{marcador}' en {RED_CR_SCRIPT}. "
            f"El script puede haber cambiado."
        )
    fin = script.find('\n', idx) + 1
    script = script[:fin]

    cwd_previo = os.getcwd()
    try:
        os.chdir(EXCEL_DIR)
        ns = {'__name__': '__main__'}
        exec(script, ns)
    finally:
        os.chdir(cwd_previo)

    return ns['Red_CR1']


def build_E5_CR_MIN():
    net = _build_cr('Min')
    meta = {
        'id': 'E5', 'red': 'Costa Rica', 'nombre': 'MIN',
        'modelo': 'Oficial (ICE)',
        'proposito': 'Escala + red real en demanda mínima',
        'condicion_inicial': 'Base_CR_Min_2023Marzo.xlsx',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus) - len(BARRAS_AISLADAS_CR),
        'n1_elemento': 'línea más cargada (determinada en Día 7)',
    }
    return net, meta


def build_E6_CR_MED():
    net = _build_cr('Med')
    meta = {
        'id': 'E6', 'red': 'Costa Rica', 'nombre': 'MED',
        'modelo': 'Oficial (ICE)',
        'proposito': 'Comparación entre escenarios de demanda',
        'condicion_inicial': 'Base_CR_Med_2023Marzo.xlsx',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus) - len(BARRAS_AISLADAS_CR),
        'n1_elemento': 'línea más cargada (determinada en Día 7)',
    }
    return net, meta


def build_E7_CR_MAX():
    net = _build_cr('Max')
    meta = {
        'id': 'E7', 'red': 'Costa Rica', 'nombre': 'MAX',
        'modelo': 'Oficial (ICE)',
        'proposito': 'Estrés operativo real en demanda máxima',
        'condicion_inicial': 'Base_CR_Max_2023Marzo.xlsx',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus) - len(BARRAS_AISLADAS_CR),
        'n1_elemento': 'línea más cargada (determinada en Día 7)',
    }
    return net, meta


BUILDERS = [
    build_E1_IEEE14_ORIGINAL,
    build_E2_IEEE14_BASE,
    build_E3_IEEE14_SUBTENSION,
    build_E4_IEEE14_SOBRECARGA,
    build_E5_CR_MIN,
    build_E6_CR_MED,
    build_E7_CR_MAX,
]


# ═════════════════════════════════════════════════════════════════════════
# MAIN — ejecutar directamente para ver tabla de viabilidad
# ═════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print("ESCENARIOS GENÉRICOS — Viabilidad por red IEEE")
    print("=" * 70)

    todos = construir_todos_ieee()
    df = resumen_viabilidad(todos)

    print("\n")
    print(df.to_string(index=False))

    # Exportar a Excel
    out = 'viabilidad_escenarios_ieee.xlsx'
    df.to_excel(out, index=False, sheet_name='Viabilidad')
    print(f"\n→ Exportado a {out}")
