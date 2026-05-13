"""
diagnosticar_barras_cr.py — Día 4 (desvío)

Diagnóstico de las 11 barras sin resultado en la red de CR.

Estrategia:
1. Construir la red para cada escenario (Min/Med/Max) usando los builders de escenarios.py
2. Identificar qué barras tienen in_service=True pero vm_pu=NaN en res_bus
3. Clasificar cada una: aislada topológicamente / sin elementos activos / otro
4. Reportar por escenario y comparar los 3

Este script importa desde escenarios.py — asegurate de que escenarios.py esté
en la misma carpeta y que su bloque CONFIG apunte correctamente a red_cr.py.
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import pandapower as pp
import pandapower.topology as top
import networkx as nx
from collections import Counter

from escenarios import build_E5_CR_MIN, build_E6_CR_MED, build_E7_CR_MAX


def reporte_completo(net, escenario):
    print(f"\n{'='*70}")
    print(f"DIAGNÓSTICO — Escenario {escenario}")
    print(f"{'='*70}")
    
    # Conteos globales
    n_bus_total = len(net.bus)
    n_bus_in_service = net.bus.in_service.sum()
    n_bus_out = n_bus_total - n_bus_in_service
    n_res = len(net.res_bus.dropna(subset=['vm_pu']))
    
    print(f"\n[1] Barras totales en net.bus: {n_bus_total}")
    print(f"    - in_service=True : {n_bus_in_service}")
    print(f"    - in_service=False: {n_bus_out}")
    print(f"[2] Barras con resultado (vm_pu no NaN): {n_res}")
    print(f"[3] Brecha (bus totales - con resultado): {n_bus_total - n_res}")
    
    # Identificar barras huérfanas
    mask_in_service = net.bus.in_service == True
    buses_in_service = net.bus[mask_in_service].index
    
    buses_sin_resultado = []
    for b in buses_in_service:
        vm = net.res_bus.loc[b, 'vm_pu'] if b in net.res_bus.index else None
        if pd.isna(vm):
            buses_sin_resultado.append(b)
    
    print(f"\n[4] Barras in_service=True pero SIN resultado: {len(buses_sin_resultado)}")
    
    if not buses_sin_resultado:
        print("    ✅ No hay barras huérfanas")
        return None
    
    # Clasificar cada barra huérfana
    print(f"\n[5] Análisis barra por barra:")
    print(f"    {'Bus ID':>8} {'vn_kv':>8} {'Nombre':<25} {'Motivo probable'}")
    print(f"    {'-'*8} {'-'*8} {'-'*25} {'-'*40}")
    
    ext_grid_buses = set(net.ext_grid[net.ext_grid.in_service == True].bus.tolist())
    slack_gens = set(net.gen[(net.gen.in_service == True) & (net.gen.slack == True)].bus.tolist()) \
        if 'slack' in net.gen.columns else set()
    slack_buses = ext_grid_buses | slack_gens
    
    g = top.create_nxgraph(net, respect_switches=True)
    buses_alimentados = set()
    for slack in slack_buses:
        if slack in g.nodes:
            buses_alimentados |= nx.node_connected_component(g, slack)
    
    clasificacion = {}
    for b in buses_sin_resultado:
        vn = net.bus.loc[b, 'vn_kv']
        nombre = str(net.bus.loc[b, 'name']) if 'name' in net.bus.columns else '-'
        
        lines_from = len(net.line[(net.line.from_bus == b) & net.line.in_service])
        lines_to = len(net.line[(net.line.to_bus == b) & net.line.in_service])
        trafos_hv = len(net.trafo[(net.trafo.hv_bus == b) & net.trafo.in_service])
        trafos_lv = len(net.trafo[(net.trafo.lv_bus == b) & net.trafo.in_service])
        trafo3_hv = len(net.trafo3w[(net.trafo3w.hv_bus == b) & net.trafo3w.in_service])
        trafo3_mv = len(net.trafo3w[(net.trafo3w.mv_bus == b) & net.trafo3w.in_service])
        trafo3_lv = len(net.trafo3w[(net.trafo3w.lv_bus == b) & net.trafo3w.in_service])
        n_elem = lines_from + lines_to + trafos_hv + trafos_lv + trafo3_hv + trafo3_mv + trafo3_lv
        
        if b not in buses_alimentados:
            motivo = "AISLADA (no conectada al slack)"
            categoria = "aislada"
        elif n_elem == 0:
            motivo = "SIN ELEMENTOS ACTIVOS"
            categoria = "sin_elementos"
        else:
            motivo = f"OTRO — {n_elem} elementos, revisar"
            categoria = "otro"
        
        clasificacion[b] = {'vn_kv': vn, 'name': nombre[:25], 'motivo': motivo,
                           'categoria': categoria}
        print(f"    {b:>8.0f} {vn:>8.2f} {nombre[:25]:<25} {motivo}")
    
    print(f"\n[6] Resumen por categoría:")
    cats = Counter([v['categoria'] for v in clasificacion.values()])
    for cat, n in cats.items():
        print(f"    {cat:20s}: {n}")
    
    return clasificacion


def main():
    resultados = {}
    builders = [('Min', build_E5_CR_MIN),
                ('Med', build_E6_CR_MED),
                ('Max', build_E7_CR_MAX)]
    
    for esc, builder in builders:
        try:
            print(f"\nConstruyendo red para escenario {esc}...")
            net, _ = builder()
            resultados[esc] = reporte_completo(net, esc)
        except Exception as e:
            print(f"\n❌ Error en escenario {esc}: {e}")
            import traceback
            traceback.print_exc()
    
    # Comparativa
    print(f"\n\n{'='*70}")
    print("COMPARATIVA ENTRE ESCENARIOS")
    print(f"{'='*70}")
    
    if all(v is not None for v in resultados.values()):
        buses_min = set(resultados['Min'].keys())
        buses_med = set(resultados['Med'].keys())
        buses_max = set(resultados['Max'].keys())
        
        print(f"\nBarras huérfanas por escenario:")
        print(f"  Min: {len(buses_min)} barras")
        print(f"  Med: {len(buses_med)} barras")
        print(f"  Max: {len(buses_max)} barras")
        
        comun = buses_min & buses_med & buses_max
        print(f"\nComún a los 3 escenarios: {len(comun)} barras")
        if comun:
            print(f"  IDs: {sorted(comun)}")


if __name__ == '__main__':
    main()
