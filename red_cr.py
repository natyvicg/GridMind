import pandapower as pp
import pandapower.plotting as pplot
import pandapower.plotting.plotly as pplotly
from pandapower.plotting.plotly import pf_res_plotly
from pandapower.networks import mv_oberrhein
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pandapower.plotting.plotly import simple_plotly
from pandapower.pf.runpp_3ph import runpp_3ph
import pandas as pd
import re
import numpy as np
import networkx as nx



base_datos = pd.read_excel('Base_CR_Max_2023-Marzo.xlsx',sheet_name=None,header=None)

#base_datos = pd.read_excel('Base_CR_Med_2023-Marzo.xlsx',sheet_name=None,header=None)

#base_datos = pd.read_excel('Base_CR_Min_2023-Marzo.xlsx',sheet_name=None,header=None)

Red_CR1 = pp.create_empty_network(name='Red_CR1', f_hz=60.0, sn_mva=100)

def datos_elem(df,fil,col):
    return base_datos[df].iloc[fil,col]

def Z_base(bus):
    
    v_base = float(Red_CR1.bus.loc[bus, 'vn_kv'])**2
    P_base = 100.0 #MVA
    Z_base = v_base/P_base
    
    
    return Z_base



barras_que_hay_que_regular = {
50562: [2,18],
50658: [2,18],
50766: [2,18],
53208: [2,15],
50812: [2,21],
53510: [2,16],
54058: [2,21],
54758: [2,22],
58208: [2,21],
58310: [2,20],
53408: [2,17],
53710 : [2,21],
58214 : [2,16],
50108 : [2,19],
50208 : [2,19],
50259 : [2,23],
50260 : [2,23],
50262: [2,23],
50358: [2,20],
50360: [2,20],
50408: [2,19],
50662: [2,19],
50664: [2,19],

50671: [6,18],
50672: [6,18],
50673: [6,18],
50816: [6,18],
51110: [2,19],
51112: [2,20],
51262: [5,19],
51264: [5,19],
52008: [4,22],
52009: [4,22],
53008: [2,17],
53010: [2,20],
53012: [2,20],
53058: [2,19],
53108: [2,19],
53109: [2,19],
53110: [2,19],
53112: [2,20],
53113: [2,20],
53160: [2,20],
53258: [2,20],
53260: [2,20],
53308: [2,21],
53310: [2,20],
53410: [2,19],
53608: [2,20],
53658: [2,19],
53708: [2,17],
53764: [2,20],
54060: [2,20],
54062: [2,20],
54108: [2,21],
54208: [2,19],
54210: [2,19],
54760: [2,20],
54858: [2,20],
54860: [2,20],
56008: [2,21],
56010: [2,19],
56060: [2,19],
58160: [2,19],
58210: [2,19],
58212: [2,19],
50808: [2,20],
50814: [2,20],
50815: [2,20],


}


# BARRAS
buses = {}

list_barras = []
# Iterar sobre cada fila de 'Bus Data' y crear buses
for i in range(1, len(base_datos['Bus Data'])):
    bus_index = datos_elem('Bus Data', i, 0)  # Obtiene el índice del bus (por ejemplo, 4408)
    
    if bus_index in list_barras:
        in_service=False
    else:
        in_service= True
    
    buses[bus_index] = pp.create_bus(Red_CR1,
                                     vn_kv = float(datos_elem('Bus Data', i, 2)),
                                     name = datos_elem('Bus Data', i, 0).strip(),
                                     index=float(datos_elem('Bus Data', i, 0)), 
                                     geodata=None, 
                                     type='b', 
                                     zone=datos_elem('Bus Data',i,5),
                                     in_service=in_service,
                                     max_vm_pu=float(datos_elem('Bus Data', i, 9)),
                                     min_vm_pu=float(datos_elem('Bus Data', i, 10)), coords=None)
prop_bus = Red_CR1.bus

#CARGAS
for i in range(1, len(base_datos['Load Data'])):
    barra = int(buses[str(datos_elem('Load Data', i, 0))])
    
    if barra in [50562,50658,50766]:
        signo = -1 
    else:
        signo = 1
        
    
    pp.create_load(Red_CR1, bus = barra,
                   p_mw = signo*float(datos_elem('Load Data', i, 5)),
                   q_mvar= signo*float(datos_elem('Load Data', i, 6)),
                   sn_mva=None, 
                   name=None, scaling=1.0, index=None, 
                   in_service=int(datos_elem('Load Data', i, 2)),
                   type='wye',#PREGUNTAR !!!!!!
                   max_p_mw=None, min_p_mw=None, max_q_mvar=None,
                   min_q_mvar=None, controllable=None)

prop_load = Red_CR1.load



#GENERADORES

for i in range(1, len(base_datos['Generator Data'])):
    
    pp.create_gen(Red_CR1, bus = buses[str(datos_elem('Generator Data', i, 0))],
                  p_mw = float(datos_elem('Generator Data', i, 2)) , vm_pu= float(datos_elem('Generator Data', i, 6)),
                  sn_mva= float(datos_elem('Generator Data', i, 8)), name=None, index=None,
                  max_q_mvar= float(datos_elem('Generator Data', i, 4)), 
                  min_q_mvar= float(datos_elem('Generator Data', i, 5)),
                  min_p_mw= float(datos_elem('Generator Data', i, 17)), 
                  max_p_mw= float(datos_elem('Generator Data', i, 16)),
                  min_vm_pu=None, max_vm_pu=None, 
                  scaling=1.0, type=None, 
                  slack=False, #Preguntar
                  controllable=None, vn_kv=None, xdss_pu= float(datos_elem('Generator Data', i, 12)), 
                  rdss_pu= float(datos_elem('Generator Data', i, 11)),
                  cos_phi=None, in_service= int(datos_elem('Generator Data', i, 14)))

prop_gen = Red_CR1.gen

#LINEAS



for i in range(1, len(base_datos['Branch Data'])):
    
    b_uS_per_km = 0
    
    bus_ref = int(buses[str(datos_elem('Branch Data', i, 0))])
    z_base_linea = Z_base(bus_ref)
    
    longitud_linea = float(datos_elem('Branch Data', i, 15))
    
    r_ohm_per_km = x_ohm_per_km = c_nf_per_km = 0.0

    # Solo calcular si la longitud no es 0
    if longitud_linea != 0.0:
        
        # zbase*X/long
        r_ohm_per_km = (z_base_linea * float(datos_elem('Branch Data', i, 3))) / longitud_linea
        x_ohm_per_km = (z_base_linea * float(datos_elem('Branch Data', i, 4))) / longitud_linea
        #B/Zbase*long
        b_siemens_per_km = (float(datos_elem('Branch Data', i, 5))) / (z_base_linea*longitud_linea)
        
        #c_nf_per_km = b_siemens_per_km
        c_nf_per_km = (b_siemens_per_km/(2*np.pi*60))*(1000**3)
        length = float(datos_elem('Branch Data', i, 15))
        
    else:
        pp.create_switch(Red_CR1,buses[str((datos_elem('Branch Data', i, 0))).strip()],
                         buses[str(datos_elem('Branch Data', i, 1)).strip()],'b',
                         int(datos_elem('Branch Data', i, 13)),
                         z_ohm = (z_base_linea * float(datos_elem('Branch Data', i, 4))))
        continue
        
    
    if float(datos_elem('Branch Data', i, 6)) != 0.0:
        max_i_ka = float(datos_elem('Branch Data', i, 8))/(np.sqrt(3)*float(Red_CR1.bus.loc[bus_ref, 'vn_kv'])) #MVA/raiz3*V uso emergencia 3 como maxima
    else:
        max_i_ka = 2.0

    
    pp.create_line_from_parameters(Red_CR1,
                                   from_bus = buses[str((datos_elem('Branch Data', i, 0))).strip()],
                                   to_bus = buses[str(datos_elem('Branch Data', i, 1)).strip()],
                                   length_km = length,
                                   r_ohm_per_km = r_ohm_per_km,
                                   x_ohm_per_km = x_ohm_per_km,
                                   c_nf_per_km = c_nf_per_km,
                                   #max i= mva/sqrt3*Vbasekv
                                   #usar menor
                                   max_i_ka = max_i_ka,
                                   name=None,
                                   index=None, type='ol', 
                                   geodata=None, 
                                   in_service= int(datos_elem('Branch Data', i, 13)), 
                                   df=1.0,
                                   parallel=1, #g_us_per_km=0.0,
                                   max_loading_percent=None, alpha=None,
                                   temperature_degree_celsius=None,
                                   #b_uS_per_km = b_siemens_per_km*(1000**2)
                                   )
    
    
prop_line = Red_CR1.line     
prop_switch = Red_CR1.switch                              



#trafos 2w

for i in range(1, len(base_datos['Trafos'])):
    

    vn_hv = None
    vn_lv = None
    
    if float(datos_elem('Trafos', i, 25)) == 0.000:
        vn_hv = Red_CR1.bus.loc[buses[str(datos_elem('Trafos', i, 0)).strip()], 'vn_kv']
    else:
        vn_hv = float(datos_elem('Trafos', i, 25))
    
    
    if float(datos_elem('Trafos', i, 42)) == 0.000:
        vn_lv = Red_CR1.bus.loc[buses[str(datos_elem('Trafos', i, 1)).strip()], 'vn_kv']
    else:
        vn_lv = float(datos_elem('Trafos', i, 42))
    

    tap_side = None
    
    if str(datos_elem('Trafos', i, 31)).strip() == str(datos_elem('Trafos', i, 0)).strip():
        tap_side = 'hv'
    elif  str(datos_elem('Trafos', i, 31)).strip() == str(datos_elem('Trafos', i, 1)).strip():
        tap_side = 'lv'
    else:
        tap_side = None
    
    tap_max = int(datos_elem('Trafos', i, 36))
    tap_neutral = int((tap_max - 2)/2)
    tap_pos = tap_neutral + 2
    
    sn=float(datos_elem('Trafos', i, 27))
    pu = float(datos_elem('Trafos', i, 22))

    
    barra_lv = int(buses[str(datos_elem('Trafos', i, 1)).strip()])
    if barra_lv in barras_que_hay_que_regular.keys():
        tap_pos = barras_que_hay_que_regular[barra_lv][0]
    else:
        tap_pos = 2
    
    pp.create_transformer_from_parameters(Red_CR1,
                                          hv_bus = int(buses[str(datos_elem('Trafos', i, 0)).strip()]), 
                                          lv_bus = barra_lv, 
                                          sn_mva = sn, 
                                          vn_hv_kv = vn_hv, 
                                          vn_lv_kv = vn_lv, 
                                          vkr_percent = 0, 
                                          vk_percent = pu*100 if pu*100 < 50 else 14.99,  #float(datos_elem('Trafos', i, 22))*100,
                                          pfe_kw = 0, 
                                          i0_percent=0,

                                          tap_side = tap_side,
                                          tap_neutral = 3, 
                                          tap_max= 6, 
                                          tap_min=1, 
                                          tap_step_percent=2.5, 
                                          #tap_step_degree=None, 
                                          tap_pos= tap_pos,
                                          tap_changer_type= 'Ratio',
                                          #tap_phase_shifter=False, 
                                          in_service=int(datos_elem('Trafos', i, 11)), 
                                          name = datos_elem('Trafos', i, 10), 
                                          index=None, 
                                          #max_loading_percent=None, 
                                          #parallel=1, df=1.0,
                                          #vector_group = str(datos_elem('Trafos', i, 20)).replace("'"," ").strip(),
                                          )



prop_trafo2w = Red_CR1.trafo


def tap(df, columna,i):
    
    tap_side = None
    
    if str(datos_elem(df, i, columna)).strip() == str(datos_elem(df, i, 0)).strip():
        tap_side = 'hv'
    elif  str(datos_elem(df, i, columna)).strip() == str(datos_elem(df, i, 1)).strip():
        tap_side = 'mv'
    elif  str(datos_elem(df, i, columna)).strip() == str(datos_elem(df, i, 2)).strip():
        tap_side = 'lv'    
    return tap_side

#trafos 3W

for i in range(1, len(base_datos['Trafos 3W'])):
    
   
    vn_hv = None
    vn_lv = None
    vn_mv = None
    tap_pos = None
    tap_side = None
    
    for j in range(3):
        
        if j == 0:
            tap_side = tap('Trafos 3W',39,i)
        elif j == 1:
            tap_side = tap('Trafos 3W',56,i)
        elif j == 2:
            tap_side = tap('Trafos 3W',73,i)
        
        if tap_side != None:
            break
     

    if tap_side == 'hv':
        tap_max = float(datos_elem('Trafos 3W', i, 44))
    elif tap_side == 'mv':
        tap_max = float(datos_elem('Trafos 3W', i, 61))
    elif tap_side == 'lv':
        tap_max = float(datos_elem('Trafos 3W', i, 78))
    
    tap_neutral = None
    tap_pos = None
    if tap_side:
        tap_neutral = int((tap_max-2)/2)
        tap_pos = tap_neutral + 2
        
    
    
    if float(str(datos_elem('Trafos 3W', i, 33)).strip()) == 0.000:
        vn_hv = Red_CR1.bus.loc[buses[str(datos_elem('Trafos 3W', i, 0)).strip()], 'vn_kv']
    else:
        vn_hv = float(str(datos_elem('Trafos 3W', i, 33)).strip())
    
    
    if float(str(datos_elem('Trafos 3W', i, 50)).strip()) == 0.000:
        vn_mv = Red_CR1.bus.loc[buses[str(datos_elem('Trafos 3W', i, 1)).strip()], 'vn_kv']
    else:
        vn_mv = float(str(datos_elem('Trafos 3W', i, 50)).strip())
        
    if float(str(datos_elem('Trafos 3W', i, 67)).strip()) == 0.000:
        vn_lv = Red_CR1.bus.loc[buses[str(datos_elem('Trafos 3W', i, 2)).strip()], 'vn_kv']
    else:
        vn_lv = float(str(datos_elem('Trafos 3W', i, 67)).strip())
    
    sn1=float(datos_elem('Trafos 3W', i, 35))
    sn2=float(datos_elem('Trafos 3W', i, 52))
    sn3=float(datos_elem('Trafos 3W', i, 69))
    pu1 = float(datos_elem('Trafos 3W', i, 22))
    pu2 = float(datos_elem('Trafos 3W', i, 25))
    pu3 = float(datos_elem('Trafos 3W', i, 28))
    
    barra_mv = int(buses[str(datos_elem('Trafos 3W', i, 1)).strip()])
    if barra_mv in barras_que_hay_que_regular.keys():
        tap_pos = barras_que_hay_que_regular[barra_mv][1] 
    else:
        tap_pos = 18
        
    pp.create_transformer3w_from_parameters(Red_CR1, 
                                            hv_bus = int(buses[str(datos_elem('Trafos 3W', i, 0)).strip()]), 
                                            mv_bus = int(buses[str(datos_elem('Trafos 3W', i, 1)).strip()]), 
                                            lv_bus = int(buses[str(datos_elem('Trafos 3W', i, 2)).strip()]), 
                                            vn_hv_kv = vn_hv, 
                                            vn_mv_kv = vn_mv, 
                                            vn_lv_kv = vn_lv, 
                                            sn_hv_mva = float(str(datos_elem('Trafos 3W', i, 37)).strip()), 
                                            sn_mv_mva =float(str(datos_elem('Trafos 3W', i, 54)).strip()), 
                                            sn_lv_mva = float(str(datos_elem('Trafos 3W', i, 71)).strip()), 
                                            vk_hv_percent = pu1*100, 
                                            vk_mv_percent = pu2*100, 
                                            vk_lv_percent = pu3*100, 
                                            vkr_hv_percent = 0.0, 
                                            vkr_mv_percent = 0.0, 
                                            vkr_lv_percent = 0.0, 
                                            pfe_kw = 0, 
                                            i0_percent = 0, 
                                            shift_mv_degree= float(str(datos_elem('Trafos 3W', i, 51)).strip()), 
                                            shift_lv_degree= float(str(datos_elem('Trafos 3W', i, 68)).strip()), 
                                            tap_side= tap_side, 
                                            tap_step_percent = 2.5, 
                                            tap_step_degree = None, 
                                            tap_pos = tap_pos, 
                                            tap_neutral=17, 
                                            tap_max = 33, 
                                            tap_min = 1, 
                                            tap_changer_type= 'Ratio',
                                            name = str(datos_elem('Trafos 3W', i, 10)), 
                                            in_service = int(datos_elem('Trafos 3W', i, 11)), 
                                            index=None, 
                                            max_loading_percent=None, 
                                            tap_at_star_point=False,
                                            vector_group = datos_elem('Trafos 3W', i, 20).replace("'"," ").strip())

prop_trafo3w = Red_CR1.trafo3w


barras_a_desconectar_shunt =[]
for i in range(1, len(base_datos['Switched Shunt Data'])):
    barra = buses[str(datos_elem('Switched Shunt Data', i, 0)).strip()]
    if barra in barras_a_desconectar_shunt:
        signo = 0
    else:
        signo = -1
    pp.create.create_shunt(Red_CR1, bus = barra,
                           q_mvar = signo*datos_elem('Switched Shunt Data', i, 11),
                           p_mw=0.0, 
                           vn_kv=None,
                           step= float(datos_elem('Switched Shunt Data', i, 10).replace("'"," ").strip()),
                           max_step= float(datos_elem('Switched Shunt Data', i, 10).replace("'"," ").strip()), 
                           name=None, step_dependency_table=False, 
                           id_characteristic_table=None, in_service=int(datos_elem('Switched Shunt Data', i,3)), 
                           index=None)
prop_shunt = Red_CR1.shunt
'''
with pd.ExcelWriter('Elements.xlsx') as writer:
    prop_bus.to_excel(writer, sheet_name= 'Bus', index = False)
    prop_load.to_excel(writer, sheet_name= 'Load', index = False)
    prop_gen.to_excel(writer, sheet_name= 'Gen', index = False)
    prop_line.to_excel(writer, sheet_name= 'Line', index = False)
    prop_trafo2w.to_excel(writer, sheet_name= 'Trafo2w', index = False)
   # prop_trafo3w.to_excel(writer, sheet_name= 'Trafo3w', index = False)
    '''

pp.create.create_ext_grid(Red_CR1, bus = 50000, vm_pu=1.0, va_degree=0.0, name='Nicaragua 1', in_service=True)
pp.create.create_ext_grid(Red_CR1, bus = 50050, vm_pu=1.0, va_degree=0.0, name='Nicaragua 2', in_service=True)
pp.create.create_ext_grid(Red_CR1, bus = 56050, vm_pu=1.0, va_degree=0.0, name='Panama 1', in_service=True)
pp.create.create_ext_grid(Red_CR1, bus = 58350, vm_pu=1.0, va_degree=0.0, name='Panama 2', in_service=True)
pp.create.create_ext_grid(Red_CR1, bus = 56052, vm_pu=1.0, va_degree=0.0, name='Panama 3', in_service=True)
#56052

#islas = list(pp.topology.unsupplied_buses(Red_CR1))
#Red_CR1.bus.loc[islas, 'in_service'] = False
#result = pp.diagnostic(Red_CR1, report_style='detailed', warnings_only=True, return_result_dict=True)
pp.runpp(Red_CR1, algorithm='nr')



result_bus = Red_CR1.res_bus
result_linea = Red_CR1.res_line
result_trafo = Red_CR1.res_trafo
result_trafo3w = Red_CR1.res_trafo3w
result_carga = Red_CR1.res_load
result_gen = Red_CR1.res_gen

#print(base_datos['Bus Data'][7])

s = (base_datos['Bus Data'].iloc[1:, [0, 7]]     # [ID, Tension]
       .set_index(0)[7])
s1 = (base_datos['Bus Data'].iloc[1:, [0, 1]]     # [ID, Tension]
       .set_index(0)[1])

s2 = (base_datos['Bus Data'].iloc[1:, [0, 2]]     # [ID, Tension]
       .set_index(0)[2])


# Asegurar mismo tipo de índice que result_bus (tú creaste buses con float)
s.index = s.index.astype(float)
s1.index = s1.index.astype(float)
s2.index = s2.index.astype(float)

# Reindexar para alinear etiquetas con las de result_bus
result_bus['Tension en BD'] = s.reindex(result_bus.index)
result_bus['Nombre'] = s1.reindex(result_bus.index)
result_bus['Voltage kV'] = s2.reindex(result_bus.index)
result_linea['Barra desde'] = prop_line['from_bus']
result_linea['Barra hacia'] = prop_line['to_bus']

result_trafo['Barra HV'] = prop_trafo2w['hv_bus']
result_trafo['Barra LV'] = prop_trafo2w['lv_bus']

result_trafo3w['Barra HV'] = prop_trafo3w['hv_bus']
result_trafo3w['Barra MV'] = prop_trafo3w['mv_bus']
result_trafo3w['Barra LV'] = prop_trafo3w['lv_bus']

result_carga['Barra'] = prop_load['bus']

result_gen['Barra'] = prop_gen['bus']

with pd.ExcelWriter('Resultados.xlsx', engine='xlsxwriter') as writer:
    # Exportar todas las hojas normalmente
    result_bus.to_excel(writer, sheet_name='Barra', index=True)
    result_carga.to_excel(writer, sheet_name='Load', index=False)
    result_gen.to_excel(writer, sheet_name='Gen', index=False)
    result_linea.to_excel(writer, sheet_name='Line', index=False)
    result_trafo.to_excel(writer, sheet_name='Trafo2w', index=False)
    result_trafo3w.to_excel(writer, sheet_name='Trafo3w', index=False)

    # === Formato condicional para la hoja de barras ===
    workbook  = writer.book
    worksheet = writer.sheets['Barra']

    # Localizar columna vm_pu en result_bus
    vm_col_idx = result_bus.columns.get_loc('vm_pu')  # índice basado en 0
    from xlsxwriter.utility import xl_col_to_name
    vm_col_letter = xl_col_to_name(vm_col_idx + 1)  # +1 porque to_excel incluye el índice

    # Crear formato rojo para celdas fuera de rango
    red_fmt = workbook.add_format({'bg_color': '#FF0000'})  # rojo claro
    amarillo_fmt = workbook.add_format({'bg_color': '#FFFF00'})

    # Rango de celdas de vm_pu (empieza en fila 2 por encabezados)
    nrows = len(result_bus) + 1
    vm_range = f'{vm_col_letter}2:{vm_col_letter}{nrows}'

    # vm_pu < 0.95
    worksheet.conditional_format(vm_range, {
        'type': 'cell',
        'criteria': '<',
        'value': 0.95,
        'format': red_fmt
    })

    # vm_pu > 1.05
    worksheet.conditional_format(vm_range, {
        'type': 'cell',
        'criteria': '>',
        'value': 1.05,
        'format': amarillo_fmt
    })

    
if not Red_CR1.res_bus.empty:
    print(f"Vmin={Red_CR1.res_bus.vm_pu.min():.4f} pu, Vmax={Red_CR1.res_bus.vm_pu.max():.4f} pu")
if not Red_CR1.res_line.empty:
    print(f"Line loading max={Red_CR1.res_line.loading_percent.max():.2f}%")
if not Red_CR1.res_trafo.empty:
    print(f"Trafo loading max={Red_CR1.res_trafo.loading_percent.max():.2f}%")
if not Red_CR1.res_trafo3w.empty:
    print(f"Trafo3W loading max={Red_CR1.res_trafo3w.loading_percent.max():.2f}%")

idx = [float(b) for b in barras_que_hay_que_regular.keys()]


'''
# tomar resultados de tensión y ángulo
out = Red_CR1.res_bus.loc[idx, ["vm_pu", "va_degree"]].copy()

# si además quieres el kV real en barra (vn_kv * vm_pu)
out["vn_kv"] = Red_CR1.bus.loc[idx, "vn_kv"]
out["V_kV"] = out["vn_kv"] * out["vm_pu"]

print(out.round(4))
'''
#--------------------------------------------
#------------------GRAFICOS-----------------

'''

tamaño_sim = 0.05
pp.plotting.simple_plot(Red_CR1, respect_switches=True, 
                        line_width=0.01, bus_size=0.5, 
                        ext_grid_size=tamaño_sim, trafo_size=0.0005,
                        plot_loads=True, plot_sgens=True,
                        load_size=0.5, sgen_size=tamaño_sim, 
                        switch_size=tamaño_sim, switch_distance=0.01, 
                        plot_line_switches=True, scale_size=True, 
                        bus_color='b', line_color='grey',
                        trafo_color='k', ext_grid_color='y', 
                        switch_color='k', library='igraph', 
                        show_plot=True, ax=None)





 
pp.plotting.plotly.pf_res_plotly(Red_CR1, cmap='Jet', on_map=False,
                                 projection=None, map_style='basic', figsize=1, 
                                 aspectratio='auto', line_width=2, bus_size=10, 
                                 filename='Red_CR1.html')
'''