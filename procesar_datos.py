import pandas as pd
import re
import os
import tkinter as tk
from tkinter import filedialog


df_bus =  pd.DataFrame(columns=['Barra','Nombre','Base KV','Code','Area num','Zone num','Owner num','Voltage (pu)','Angle (deg)','Normal Vmax (pu)','Normal Vmin (pu)','Emergency Vmax (pu)','Emergency Vmin (pu)'])
df_load =  pd.DataFrame(columns=['Barra','ID','In service','Area num','Zone Num','P (MW)','Q (Mvar)','Ipload (pu)', 'Iqload (pu)','Ypload (pu)','Yqload (pu)','Owner (pu)','Scalable','Interruptible'])

df_shunt = pd.DataFrame()
df_gen = pd.DataFrame()
df_branch = pd.DataFrame()
df_sw = pd.DataFrame()

# Especifica la cadena que estás buscando dentro de las líneas
cadena_objetivo = "ARCHIVO CENCE"

# ==== Seleccionar archivo con Tkinter ====
root = tk.Tk()
root.withdraw()                    # Ocultamos la ventana principal
root.attributes('-topmost', True)  # La ponemos por encima de todo
root.update()                      # Forzamos actualización para que se aplique

ruta_archivo = filedialog.askopenfilename(
    parent=root,
    title="Seleccione el archivo de texto de CENCE",
    filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")]
)

if not ruta_archivo:
    root.destroy()
    raise SystemExit("No se seleccionó ningún archivo. Saliendo del programa...")

# Carpeta donde está el archivo de entrada
carpeta_entrada = os.path.dirname(ruta_archivo)

# ==== Seleccionar carpeta de salida ====
carpeta_salida = filedialog.askdirectory(
    parent=root,
    title="Seleccione la carpeta de salida",
    initialdir=carpeta_entrada
)

# Si el usuario cancela la selección, usamos la carpeta del archivo de entrada
if not carpeta_salida:
    carpeta_salida = carpeta_entrada

root.destroy()  # Ya no necesitamos la ventana de Tk

# ==== Construir nombre de salida basado en el archivo original ====
nombre_sin_ext = os.path.splitext(os.path.basename(ruta_archivo))[0]
nombre_salida = os.path.join(carpeta_salida, f"{nombre_sin_ext}.xlsx")

# Abre el archivo seleccionado en modo lectura
with open(ruta_archivo, 'r', encoding='utf-8') as archivo:
    # Itera sobre cada línea
    for linea in archivo:
        # Si la cadena objetivo es encontrada en la línea, rompe el ciclo
        if cadena_objetivo in linea:
            break

    # Ahora puedes procesar el archivo desde la siguiente línea
    for linea in archivo:
        if 'End of Bus data' in linea:
            break

        linea = linea.strip()
        elementos = linea.split(',')

        fila_df = pd.DataFrame(
            [elementos],
            columns=['Barra','Nombre','Base KV','Code','Area num','Zone num',
                     'Owner num','Voltage (pu)','Angle (deg)','Normal Vmax (pu)',
                     'Normal Vmin (pu)','Emergency Vmax (pu)','Emergency Vmin (pu)']
        )
        df_bus = pd.concat([df_bus, fila_df], ignore_index=False, axis=0)
    
    for linea in archivo:
        if 'End of Load data' in linea:
            break

        linea = linea.strip()
        elementos = linea.split(',')

        fila_df = pd.DataFrame(
            [elementos],
            columns=['Barra','ID','In service','Area num','Zone Num','P (MW)',
                     'Q (Mvar)','Ipload (pu)', 'Iqload (pu)','Ypload (pu)',
                     'Yqload (pu)','Owner (pu)','Scalable','Interruptible']
        )
        df_load = pd.concat([df_load, fila_df], ignore_index=False, axis=0)
        
    for linea in archivo:
        if 'End of Fixed shunt data' in linea:
            break

        linea = linea.strip()
        elementos = linea.split(',')

        fila_df = pd.DataFrame([elementos])
        df_shunt = pd.concat([df_shunt, fila_df], ignore_index=True, axis=0)
        
    for linea in archivo:
        if 'End of Generator data' in linea:
            break

        linea = linea.strip()
        elementos = linea.split(',')

        fila_df = pd.DataFrame(
            [elementos],
            columns=['Barra','ID','PGen (MW)','Qgen (Mvar)','Qmax (Mvar)',
                     'Qmin (Mvar)','Vsetpoint (pu)','Owner','Mbase (MVA)',
                     'R source (pu)','X Source (pu)','Rtran (pu)','Xtran (pu)',
                     'Gentap (pu)','In service','RMPCT','Pmax (MW)','Pmin (MW)',
                     'Owner','Fraction']
        )
        df_gen = pd.concat([df_gen, fila_df], ignore_index=True, axis=0)
    
    for linea in archivo:
        if 'End of Branch data' in linea:
            break

        linea = linea.strip()
        elementos = linea.split(',')

        fila_df = pd.DataFrame(
            [elementos],
            columns=['Desde','Hacia','id','R (pu)','X (pu)','B (pu)',
                     'RATE A (nominal)','RATE B','RATE C','Line G','Line B',
                     'Line G','Line B','In service','NONE','length','Owner',
                     'Fraction']
        )
        df_branch = pd.concat([df_branch, fila_df], ignore_index=True, axis=0)
   
    transformadores = []          # Lista para almacenar los datos de cada transformador
    transformador_actual = []     # Lista para acumular los datos de un transformador

    # Patrón para identificar el inicio de un transformador
    patron_inicio = re.compile(r'^\s*\d+,\s*\d+')    
    
    for linea in archivo:
        if 'End of Transformer data' in linea:
            break
        
        if patron_inicio.match(linea):  # Detecta el inicio de un nuevo transformador
            if transformador_actual:    # Guarda el transformador acumulado anterior
                transformadores.append(transformador_actual)
                transformador_actual = []  # Reinicia la lista para el nuevo transformador
        
        transformador_actual.extend(linea.strip().split(','))  # Acumula los datos de la línea actual
    
    # Agregar el último transformador si existe (fuera del bucle)
    if transformador_actual:
        transformadores.append(transformador_actual)

    # Crear el DataFrame después de completar el bucle
    df_trafo = pd.DataFrame(transformadores)
        
    accion = False
    for linea in archivo:
        if 'End of Switched shunt data' in linea:
            break
        elif 'Begin Switched shunt data' in linea:
            accion = True
            continue

        if accion:
            linea = linea.strip()
            elementos = linea.split(',')

            fila_df = pd.DataFrame([elementos])
            df_sw = pd.concat([df_sw, fila_df], ignore_index=True, axis=0)
            

df_trafos3w = pd.DataFrame()
df_trafos = pd.DataFrame()

for indice, fila in df_trafo.iterrows():
    if fila[2].strip() == (0 or '0'):
        df_trafos = pd.concat([df_trafos, fila], ignore_index=True, axis=1)
    else:
        df_trafos3w = pd.concat([df_trafos3w, fila], ignore_index=True, axis=1)

df_trafos = df_trafos.T
df_trafos = df_trafos.iloc[:, :43]
df_trafos.columns = ['Desde', 'Hacia', 'Last bus', 'ID', 'Winding', 'Impedance',
                     'Admitance', 'Magnetizing G', 'Magnetizing B', 'non meterd?',
                     'Name', 'In service', 'Owner', 'Fraction', 'Owner', 'Fraction',
                     'Owner', 'Fraction', 'Owner', 'Fraction', 'Vector',
                     'W1-2 R (pu)', 'W1-2 X (pu)', 'S BASE 1-2 (MVA)',
                     'Wnd 1 Ratio (pu)', 'Wnd 1', 'Wnd Angl (deg)', 'Rate 1',
                     'Rate 2', 'Rate 3', 'Controlled mode', 'Cont1',
                     'RMA1 (pu)', 'RMI1 (pu)', 'VMA1 (pu)', 'VMI1 (pu)', 'NTP1',
                     'TAB1', 'CR2', 'CX2', 'CNXA 2', 'Wnd 3 Voltage (pu)',
                     'Wnd 3 Voltage (kv)']

df_trafos3w = df_trafos3w.T
df_trafos3w.columns = ['Desde', 'Hacia', 'Last Bus', 'ID', 'Winding', 'Impedance',
                       'Admitance', 'Magnetizing G', 'Magnetizing B', 'Non-metered',
                       'Name', 'In service', 'Owner', 'Fraction', 'Owner', 'Fraction',
                       'Owner', 'Fraction', 'Owner', 'Fraction', 'Vector',
                       'W1-2 R (pu)', 'W1-2 X (pu)', 'S BASE 1-2 (MVA)', 'W2-3 R',
                       'W2-3X', 'S BASE 2-3 (MVA)', 'W3-1 R', 'W3-1 X',
                       'S BASE 3-1 (MVA)', 'VM Star Bus (pu)', 'Ang Star Bus (deg)',
                       'Wnd 1 Voltage (pu)', 'Wnd 1 Voltage (kv)', 'Wnd 1 ang (deg)',
                       'Rate 1-1', 'Rate 1-2', 'Rate 1-3', 'control mode 1',
                       'Cont 1', 'RMA1', 'RMI1', 'VMA1', 'VMI1', 'NTP1', 'TAB1',
                       'CR1', 'CX1', 'CNXA 1', 'Wnd 2 Voltage (pu)',
                       'Wnd 2 Voltage (kv)', 'Wnd 3 ang (deg)', 'Rate 2-1',
                       'Rate 2-2', 'Rate 2-3', 'CONTROL MODE 2', 'CONT2', 'RMA2',
                       'RMI2', 'VMA2', 'VMI2', 'NTP2', 'TAB2', 'CR2', 'CX2',
                       'CNXA 2', 'Wnd 3 Voltage (pu)', 'Wnd 3 Voltage (kv)',
                       'Wnd 3 ang (deg)', 'Rate 3-1', 'Rate 3-2', 'Rate 3-3',
                       'CONTROL MODE 3', 'CONT3', 'RMA3', 'RMI3', 'VMA3', 'VMI3',
                       'NTP3', 'TAB3', 'CR3', 'CX3', 'CNXA 3']

df_sw.columns  = ['Barra', 'Control mode', 'Adjmeth', 'In service', 'Vhi', 'Vlo',
                  'swreg', 'RMPCT', 'NAME', '9', 'S_i', '11', '12', '13']

# ==== Guardar Excel con el nombre basado en el archivo original y carpeta seleccionada ====
with pd.ExcelWriter(nombre_salida) as writer:
    df_bus.to_excel(writer, sheet_name='Bus Data', index=False)
    df_load.to_excel(writer, sheet_name='Load Data', index=False)
    df_shunt.to_excel(writer, sheet_name='Shunt Data', index=False)
    df_gen.to_excel(writer, sheet_name='Generator Data', index=False)
    df_branch.to_excel(writer, sheet_name='Branch Data', index=False)
    df_trafos.to_excel(writer, sheet_name='Trafos', index=False)
    df_trafos3w.to_excel(writer, sheet_name='Trafos 3W', index=False)
    df_sw.to_excel(writer, sheet_name='Switched Shunt Data', index=False)

print(f"Archivo guardado como: {nombre_salida}")
