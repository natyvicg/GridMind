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



# (Se elimino el diccionario barras_que_hay_que_regular: las posiciones de tap
#  se leen ahora del archivo de origen, columnas WINDV1/WINDV2/WINDV3.)

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

    # Correccion: antes se invertia el signo de las cargas de las barras
    # 50562, 50658 y 50766. El archivo de origen ya trae cargas con signo
    # negativo donde corresponde (generacion embebida), asi que todas las
    # cargas se toman con el signo con que vienen.
    pp.create_load(Red_CR1, bus = barra,
                   p_mw = float(datos_elem('Load Data', i, 5)),
                   q_mvar= float(datos_elem('Load Data', i, 6)),
                   sn_mva=None, 
                   name=None, scaling=1.0, index=None, 
                   in_service=int(datos_elem('Load Data', i, 2)),
                   type='wye',
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
#
# Convenciones del archivo de origen (PSS/E v33 RAW, exportado a Excel):
#   CW = 1: las relaciones de devanado WINDV1 y WINDV2 estan en pu de la
#           tension base de la barra a la que se conecta cada devanado.
#   CZ = 1: R1-2 y X1-2 estan en pu sobre la base del sistema (100 MVA).
# pandapower pide vk_percent referido a la potencia nominal sn_mva del
# transformador, de modo que vk% = X1-2[pu, 100 MVA] * sn_mva.
# La relacion de transformacion fuera de la nominal (WINDV1/WINDV2) se
# representa con un tap en el lado de alta de un solo paso, cuyo tamano
# es exactamente esa relacion. Para los transformadores con control de
# tension (COD1 = 1) el archivo trae la posicion de tap con la que PSS/E
# resolvio el caso, asi que el modelo reproduce el estado resuelto.

for i in range(1, len(base_datos['Trafos'])):

    hv_bus = int(buses[str(datos_elem('Trafos', i, 0)).strip()])
    lv_bus = int(buses[str(datos_elem('Trafos', i, 1)).strip()])

    # Con CW = 1 las tensiones nominales de los devanados son las bases
    # de las barras; la relacion WINDV1/WINDV2 lleva todo el desfase.
    vn_hv = float(Red_CR1.bus.loc[hv_bus, 'vn_kv'])
    vn_lv_barra = float(Red_CR1.bus.loc[lv_bus, 'vn_kv'])

    sn = float(datos_elem('Trafos', i, 27))            # Rate 1 (RATA1), MVA
    r12 = float(datos_elem('Trafos', i, 21))           # R1-2, pu sobre 100 MVA
    x12 = float(datos_elem('Trafos', i, 22))           # X1-2, pu sobre 100 MVA
    windv1 = float(datos_elem('Trafos', i, 24))        # WINDV1, pu de la base de la barra
    windv2 = float(datos_elem('Trafos', i, 41))        # WINDV2, pu de la base de la barra
    if windv1 == 0.0:
        windv1 = 1.0
    if windv2 == 0.0:
        windv2 = 1.0

    # Cambio de base: pu sobre 100 MVA -> por ciento sobre sn
    vkr = r12 * sn
    vk = max((r12**2 + x12**2) ** 0.5 * sn, 0.01)

    # WINDV1 va como tap en el lado de alta; WINDV2 (igual a 1 en todos los
    # transformadores de este archivo) va en la tension nominal del devanado
    # de baja, que es como pandapower representa la relacion de ese lado.
    relacion = windv1
    vn_lv = vn_lv_barra * windv2
    pp.create_transformer_from_parameters(Red_CR1,
                                          hv_bus = hv_bus, 
                                          lv_bus = lv_bus, 
                                          sn_mva = sn, 
                                          vn_hv_kv = vn_hv, 
                                          vn_lv_kv = vn_lv, 
                                          vkr_percent = vkr, 
                                          vk_percent = vk,
                                          pfe_kw = 0, 
                                          i0_percent=0,
                                          tap_side = 'hv',
                                          tap_neutral = 0, 
                                          tap_max = 1, 
                                          tap_min = -1, 
                                          tap_step_percent = (relacion - 1.0) * 100.0, 
                                          tap_pos = 1,
                                          tap_changer_type = 'Ratio',
                                          in_service=int(datos_elem('Trafos', i, 11)), 
                                          name = datos_elem('Trafos', i, 10), 
                                          index=None, 
                                          )

prop_trafo2w = Red_CR1.trafo
#trafos 3W
#
# Mismas convenciones (CW = 1, CZ = 1). pandapower refiere cada tension de
# cortocircuito de un transformador de tres devanados a la menor de las dos
# potencias nominales de los devanados que une (build_branch.z_br_to_bus_vector):
#   vk_hv% = X1-2 * min(sn_hv, sn_mv)
#   vk_mv% = X2-3 * min(sn_mv, sn_lv)
#   vk_lv% = X3-1 * min(sn_hv, sn_lv)
# La relacion WINDV1 del devanado de alta se representa con el tap de un
# paso; WINDV2 y WINDV3 (distintas de 1 en seis casos) se representan con
# la tension nominal del devanado.

for i in range(1, len(base_datos['Trafos 3W'])):

    hv_bus = int(buses[str(datos_elem('Trafos 3W', i, 0)).strip()])
    mv_bus = int(buses[str(datos_elem('Trafos 3W', i, 1)).strip()])
    lv_bus = int(buses[str(datos_elem('Trafos 3W', i, 2)).strip()])

    sn_hv = float(str(datos_elem('Trafos 3W', i, 37)).strip())
    sn_mv = float(str(datos_elem('Trafos 3W', i, 54)).strip())
    sn_lv = float(str(datos_elem('Trafos 3W', i, 71)).strip())

    r12 = float(datos_elem('Trafos 3W', i, 21)); x12 = float(datos_elem('Trafos 3W', i, 22))
    r23 = float(datos_elem('Trafos 3W', i, 24)); x23 = float(datos_elem('Trafos 3W', i, 25))
    r31 = float(datos_elem('Trafos 3W', i, 27)); x31 = float(datos_elem('Trafos 3W', i, 28))

    windv1 = float(str(datos_elem('Trafos 3W', i, 32)).strip()) or 1.0
    windv2 = float(str(datos_elem('Trafos 3W', i, 49)).strip()) or 1.0
    windv3 = float(str(datos_elem('Trafos 3W', i, 66)).strip()) or 1.0

    vn_hv = float(Red_CR1.bus.loc[hv_bus, 'vn_kv'])
    vn_mv = float(Red_CR1.bus.loc[mv_bus, 'vn_kv']) * windv2
    vn_lv = float(Red_CR1.bus.loc[lv_bus, 'vn_kv']) * windv3

    def _vk(r, x, s):
        return max((r**2 + x**2) ** 0.5 * s, 0.01)

    pp.create_transformer3w_from_parameters(Red_CR1, 
                                            hv_bus = hv_bus, 
                                            mv_bus = mv_bus, 
                                            lv_bus = lv_bus, 
                                            vn_hv_kv = vn_hv, 
                                            vn_mv_kv = vn_mv, 
                                            vn_lv_kv = vn_lv, 
                                            sn_hv_mva = sn_hv, 
                                            sn_mv_mva = sn_mv, 
                                            sn_lv_mva = sn_lv, 
                                            vk_hv_percent = _vk(r12, x12, min(sn_hv, sn_mv)), 
                                            vk_mv_percent = _vk(r23, x23, min(sn_mv, sn_lv)), 
                                            vk_lv_percent = _vk(r31, x31, min(sn_hv, sn_lv)), 
                                            vkr_hv_percent = r12 * min(sn_hv, sn_mv), 
                                            vkr_mv_percent = r23 * min(sn_mv, sn_lv), 
                                            vkr_lv_percent = r31 * min(sn_hv, sn_lv), 
                                            pfe_kw = 0, 
                                            i0_percent = 0, 
                                            # Desfases: PSS/E da el angulo de cada devanado respecto del punto
                                            # estrella (ANG1, ANG2, ANG3); pandapower pide el atraso de mv y de lv
                                            # respecto de hv, es decir ANG1 - ANG2 y ANG1 - ANG3.
                                            shift_mv_degree= float(str(datos_elem('Trafos 3W', i, 34)).strip()) - float(str(datos_elem('Trafos 3W', i, 51)).strip()), 
                                            shift_lv_degree= float(str(datos_elem('Trafos 3W', i, 34)).strip()) - float(str(datos_elem('Trafos 3W', i, 68)).strip()), 
                                            tap_side = 'hv', 
                                            tap_step_percent = (windv1 - 1.0) * 100.0, 
                                            tap_step_degree = 0.0, 
                                            tap_pos = 1, 
                                            tap_neutral = 0, 
                                            tap_max = 1, 
                                            tap_min = -1, 
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
                           # Correccion: se usa BINIT (columna 9, Mvar conectados en el caso
                           # resuelto) y no B1 (columna 11, tamano del bloque). Signo: en PSS/E
                           # B positivo es capacitivo; en pandapower q_mvar positivo es inductivo.
                           q_mvar = signo*float(datos_elem('Switched Shunt Data', i, 9)),
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

# Fuentes ideales en las cinco barras de frontera (representacion A,
# seccion 3.3.3 del informe). Correccion: la tension y el angulo de cada
# fuente se toman de la solucion que trae el archivo de origen para esa
# barra (columnas 'Voltage (pu)' y 'Angle (deg)' de Bus Data), en lugar de
# 1,0 pu y 0 grados fijos.
_bus_data = base_datos['Bus Data']
def _v_angulo_archivo(barra):
    fila = _bus_data[_bus_data.iloc[:, 0].astype(str).str.strip() == str(barra)]
    return float(fila.iloc[0, 7]), float(fila.iloc[0, 8])

for _barra, _nombre in [(50000, 'Nicaragua 1'), (50050, 'Nicaragua 2'),
                        (56050, 'Panama 1'), (58350, 'Panama 2'), (56052, 'Panama 3')]:
    _v, _ang = _v_angulo_archivo(_barra)
    pp.create.create_ext_grid(Red_CR1, bus = _barra, vm_pu=_v, va_degree=_ang,
                              name=_nombre, in_service=True)
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

# (linea eliminada: usaba barras_que_hay_que_regular)


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