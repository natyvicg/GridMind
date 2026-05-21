"""
analizar_barras_aisladas.py — Día 4 (desvío)

Análisis detallado de las 11 barras aisladas.

Para cada barra:
- Nombre, vn_kv
- Elementos TOTALES que la tocan (in_service=True y False)
- Detalle de cada elemento: tipo, índice, estado, barra opuesta
- Cargas y generadores asociados

Este script importa desde escenarios.py — asegurate de que escenarios.py esté
en la misma carpeta y que su bloque CONFIG apunte correctamente a red_cr.py.
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
from escenarios import build_E5_CR_MIN

BARRAS_AISLADAS = [50066, 50081, 50383, 50384, 50582,
                   50930, 53130, 54881, 56082, 58324, 58326]


def analizar_barra(net, bus_id):
    """Análisis exhaustivo de una barra"""
    info = {'bus_id': bus_id}
    
    if bus_id not in net.bus.index:
        info['existe'] = False
        return info
    
    info['vn_kv'] = net.bus.loc[bus_id, 'vn_kv']
    info['in_service'] = net.bus.loc[bus_id, 'in_service']
    info['name'] = net.bus.loc[bus_id, 'name']
    
    # Líneas
    lineas_from = net.line[net.line.from_bus == bus_id]
    lineas_to = net.line[net.line.to_bus == bus_id]
    info['lineas'] = []
    for idx in lineas_from.index:
        info['lineas'].append({
            'idx': idx, 'tipo': 'line',
            'from_bus': bus_id,
            'to_bus': int(lineas_from.loc[idx, 'to_bus']),
            'in_service': bool(lineas_from.loc[idx, 'in_service']),
            'longitud_km': float(lineas_from.loc[idx, 'length_km']),
        })
    for idx in lineas_to.index:
        info['lineas'].append({
            'idx': idx, 'tipo': 'line',
            'from_bus': int(lineas_to.loc[idx, 'from_bus']),
            'to_bus': bus_id,
            'in_service': bool(lineas_to.loc[idx, 'in_service']),
            'longitud_km': float(lineas_to.loc[idx, 'length_km']),
        })
    
    # Trafos 2W
    trafos = pd.concat([
        net.trafo[net.trafo.hv_bus == bus_id],
        net.trafo[net.trafo.lv_bus == bus_id]
    ])
    info['trafos_2w'] = []
    for idx, row in trafos.iterrows():
        info['trafos_2w'].append({
            'idx': idx, 'hv_bus': int(row.hv_bus), 'lv_bus': int(row.lv_bus),
            'in_service': bool(row.in_service), 'sn_mva': float(row.sn_mva),
        })
    
    # Trafos 3W
    trafos3 = pd.concat([
        net.trafo3w[net.trafo3w.hv_bus == bus_id],
        net.trafo3w[net.trafo3w.mv_bus == bus_id],
        net.trafo3w[net.trafo3w.lv_bus == bus_id]
    ])
    info['trafos_3w'] = []
    for idx, row in trafos3.iterrows():
        info['trafos_3w'].append({
            'idx': idx, 'hv_bus': int(row.hv_bus), 'mv_bus': int(row.mv_bus),
            'lv_bus': int(row.lv_bus), 'in_service': bool(row.in_service),
        })
    
    # Cargas
    cargas = net.load[net.load.bus == bus_id]
    info['loads'] = [{'idx': idx, 'in_service': bool(row.in_service),
                      'p_mw': float(row.p_mw), 'q_mvar': float(row.q_mvar)}
                     for idx, row in cargas.iterrows()]
    
    # Generadores
    gens = net.gen[net.gen.bus == bus_id] if not net.gen.empty else pd.DataFrame()
    info['gens'] = [{'idx': idx, 'in_service': bool(row.in_service),
                     'p_mw': float(row.p_mw)}
                    for idx, row in gens.iterrows()]
    
    # sgens
    sgens = net.sgen[net.sgen.bus == bus_id] if not net.sgen.empty else pd.DataFrame()
    info['sgens'] = [{'idx': idx, 'in_service': bool(row.in_service),
                      'p_mw': float(row.p_mw)}
                     for idx, row in sgens.iterrows()]
    
    # Switches
    switches = net.switch[(net.switch.bus == bus_id) | (net.switch.element == bus_id)]
    info['switches'] = [{'idx': idx, 'bus': int(row.bus), 'element': int(row.element),
                         'et': row.et, 'closed': bool(row.closed)}
                        for idx, row in switches.iterrows()]
    
    return info


def main():
    print("Construyendo red (escenario Min — igual que Med y Max para topología)...")
    net, _ = build_E5_CR_MIN()
    
    print(f"\n{'='*80}")
    print(f"ANÁLISIS DETALLADO — 11 barras aisladas")
    print(f"{'='*80}\n")
    
    for bus_id in BARRAS_AISLADAS:
        info = analizar_barra(net, bus_id)
        
        print(f"\n{'─'*80}")
        print(f"Barra {bus_id}  (vn_kv={info['vn_kv']}, in_service={info['in_service']})")
        print(f"{'─'*80}")
        
        n_lineas = len(info['lineas'])
        n_lineas_in = sum(1 for l in info['lineas'] if l['in_service'])
        print(f"  Líneas: {n_lineas} (en servicio: {n_lineas_in})")
        for l in info['lineas']:
            est = "✅" if l['in_service'] else "❌"
            print(f"    {est} line idx={l['idx']}: {l['from_bus']} → {l['to_bus']}, {l['longitud_km']:.2f} km")
        
        n_trafos2 = len(info['trafos_2w'])
        n_trafos2_in = sum(1 for t in info['trafos_2w'] if t['in_service'])
        print(f"  Trafos 2W: {n_trafos2} (en servicio: {n_trafos2_in})")
        for t in info['trafos_2w']:
            est = "✅" if t['in_service'] else "❌"
            print(f"    {est} trafo idx={t['idx']}: hv={t['hv_bus']} → lv={t['lv_bus']}, {t['sn_mva']:.1f} MVA")
        
        n_trafos3 = len(info['trafos_3w'])
        n_trafos3_in = sum(1 for t in info['trafos_3w'] if t['in_service'])
        if n_trafos3 > 0:
            print(f"  Trafos 3W: {n_trafos3} (en servicio: {n_trafos3_in})")
            for t in info['trafos_3w']:
                est = "✅" if t['in_service'] else "❌"
                print(f"    {est} trafo3w idx={t['idx']}: hv={t['hv_bus']}, mv={t['mv_bus']}, lv={t['lv_bus']}")
        
        n_cargas = len(info['loads'])
        if n_cargas > 0:
            p_tot = sum(l['p_mw'] for l in info['loads'] if l['in_service'])
            print(f"  Cargas: {n_cargas}  (P total en servicio = {p_tot:.2f} MW)")
            for l in info['loads']:
                est = "✅" if l['in_service'] else "❌"
                print(f"    {est} load idx={l['idx']}: P={l['p_mw']:.2f} MW, Q={l['q_mvar']:.2f} MVAr")
        
        n_gens = len(info['gens'])
        if n_gens > 0:
            print(f"  Generadores: {n_gens}")
            for g in info['gens']:
                est = "✅" if g['in_service'] else "❌"
                print(f"    {est} gen idx={g['idx']}: P={g['p_mw']:.2f} MW")
        
        n_sgens = len(info['sgens'])
        if n_sgens > 0:
            print(f"  Gens estáticos: {n_sgens}")
            for g in info['sgens']:
                est = "✅" if g['in_service'] else "❌"
                print(f"    {est} sgen idx={g['idx']}: P={g['p_mw']:.2f} MW")
        
        if info['switches']:
            print(f"  Switches: {len(info['switches'])}")
            for s in info['switches']:
                est = "cerrado" if s['closed'] else "ABIERTO"
                print(f"    switch idx={s['idx']}: bus={s['bus']}, element={s['element']} (et={s['et']}), {est}")


if __name__ == '__main__':
    main()
