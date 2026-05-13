"""
escenarios.py — Definición de los 6 escenarios de validación de GridMind

E1-E3: IEEE 14 (BASE, SUBTENSIÓN, SOBRECARGA)
E4-E6: Costa Rica (Min, Med, Max)

Cada función `build_*` devuelve (net, meta):
- net: red pandapower con PF ya ejecutado
- meta: dict con metadata (id, red, nombre, propósito, condición inicial)
"""

import os
import pandas as pd
import pandapower as pp
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN — editar si la estructura de carpetas no es la default
# ═══════════════════════════════════════════════════════════════════════════

# Carpeta raíz del proyecto (por default: la misma donde vive este archivo)
GRIDMIND_DIR = Path(__file__).resolve().parent

# Ruta al script original de construcción de la red de CR
RED_CR_SCRIPT = GRIDMIND_DIR / 'red_cr.py'

# Carpeta donde están los Base_CR_*.xlsx
EXCEL_DIR = GRIDMIND_DIR

# ═══════════════════════════════════════════════════════════════════════════
# Fin configuración
# ═══════════════════════════════════════════════════════════════════════════

BARRAS_AISLADAS_CR = [50066, 50081, 50383, 50384, 50582,
                      50930, 53130, 54881, 56082, 58324, 58326]


# ─── IEEE 14 ─────────────────────────────────────────────────────────────

def _build_ieee14_base():
    """IEEE 14 con setpoint de gens a 1.02 pu y max_i_ka recalibrado a 2×base."""
    net = pp.networks.case14()
    net.gen.loc[:, 'vm_pu'] = 1.02
    net.ext_grid.loc[:, 'vm_pu'] = 1.02
    pp.runpp(net)
    for i in net.line.index:
        i_base = float(net.res_line.loc[i, 'i_ka'])
        net.line.loc[i, 'max_i_ka'] = max(i_base * 2.0, 0.1)
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
        'condicion_inicial': 'Red calibrada, gens y ext_grid en 1.02 pu, max_i_ka = 2×flujo base',
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
            net.gen.loc[idx, 'vm_pu'] = 0.95
    pp.runpp(net)
    meta = {
        'id': 'E3', 'red': 'IEEE 14', 'nombre': 'SUBTENSIÓN',
        'modelo': 'Calibrado',
        'proposito': 'Diagnóstico de tensión',
        'condicion_inicial': 'Sobre red calibrada — setpoint gens buses 6 y 8 (idx 5, 7) bajado a 0.95 pu',
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
    net.load.loc[:, 'p_mw'] = net.load.p_mw * 1.3
    net.load.loc[:, 'q_mvar'] = net.load.q_mvar * 1.3
    pp.runpp(net)
    meta = {
        'id': 'E4', 'red': 'IEEE 14', 'nombre': 'SOBRECARGA',
        'modelo': 'Calibrado',
        'proposito': 'Diagnóstico térmico + análisis N-1',
        'condicion_inicial': 'Sobre red calibrada — línea 1-5 fuera de servicio + cargas × 1.3',
        'n_barras_totales': len(net.bus),
        'n_barras_energizadas': len(net.bus[net.bus.in_service]),
        'n1_elemento': 'line más cargada remanente',
    }
    return net, meta


# ─── Costa Rica ──────────────────────────────────────────────────────────

def _detectar_nombre_excel(escenario):
    """Detecta si los xlsx están con o sin guión en la fecha."""
    candidatos = [
        f'Base_CR_{escenario}_2023Marzo.xlsx',        # sin guión
        f'Base_CR_{escenario}_2023-Marzo.xlsx',       # con guión
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
