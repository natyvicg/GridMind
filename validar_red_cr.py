"""
validar_red_cr.py
==================
 
Día 2 — Validación de la red eléctrica de Costa Rica.
 
Este script ejecuta 'red_cr.py' (código heredado, NO modificado) para los
tres escenarios de demanda (Min, Med, Max) y produce una tabla comparativa
con los resultados que serán la LÍNEA BASE contra la cual se validará el
agente GridMind en el Día 7.
 
Estrategia: 'red_cr.py' tiene hardcodeado el archivo Excel que lee
(línea 17 del script original: 'Base_CR_Max_2023-Marzo.xlsx'). Ese nombre
COINCIDE con el archivo real del escenario Max. Para correr los tres
escenarios sin modificar red_cr.py:
 
    1. Al inicio: se respalda el archivo Max original en '_backup_Max.xlsx'.
    2. Para cada escenario: se copia el archivo correspondiente sobre el
       nombre que red_cr.py espera.
    3. Al final: se restaura el archivo Max original desde el respaldo.
 
El bloque try/finally garantiza que el respaldo se restaure incluso si
alguna corrida falla. El respaldo se borra al final si todo sale bien.
 
Autoría: Natalia Víctor (B98438). El script 'red_cr.py' que este wrapper
ejecuta es material heredado del proyecto; no se modifica.
"""
 
import subprocess   # para lanzar 'red_cr.py' como proceso separado (aislamiento)
import shutil       # para copiar archivos Excel
import re           # para extraer números del stdout que imprime red_cr.py
import pandas as pd # para leer Resultados.xlsx y armar la tabla final
import os
 
# =============================================================================
# Configuración
# =============================================================================
 
# Nombre del archivo que 'red_cr.py' espera leer (línea 17 del script original).
# Coincide con el nombre real del archivo del escenario Max.
ARCHIVO_LECTURA = "Base_CR_Max_2023-Marzo.xlsx"
 
# Respaldo temporal del archivo Max original (se crea al inicio, se borra al final).
ARCHIVO_RESPALDO = "_backup_Max_original.xlsx"
 
# Escenarios a validar. El orden importa solo por cómo aparece en la tabla final.
ESCENARIOS = ["Min", "Med", "Max"]
 
def archivo_fuente(escenario):
    """Devuelve el nombre del archivo Excel original para un escenario dado."""
    return f"Base_CR_{escenario}_2023-Marzo.xlsx"
 
# Criterios de aceptación (estándar para sistemas de transmisión)
V_MIN_PU = 0.95
V_MAX_PU = 1.05
LOADING_MAX_PCT = 100.0
 
 
# =============================================================================
# Funciones auxiliares
# =============================================================================
 
def parsear_stdout(texto):
    """
    Extrae las métricas que red_cr.py imprime al final de su ejecución.
    Las líneas relevantes tienen el formato exacto del script original:
        Vmin=X.XXXX pu, Vmax=X.XXXX pu
        Line loading max=XX.XX%
        Trafo loading max=XX.XX%
        Trafo3W loading max=XX.XX%
    """
    def extraer(patron):
        m = re.search(patron, texto)
        return float(m.group(1)) if m else None
 
    return {
        "vmin":        extraer(r"Vmin=([\d.]+)"),
        "vmax":        extraer(r"Vmax=([\d.]+)"),
        "line_max":    extraer(r"Line loading max=([\d.]+)"),
        "trafo_max":   extraer(r"Trafo loading max=([\d.]+)"),
        "trafo3w_max": extraer(r"Trafo3W loading max=([\d.]+)"),
    }
 
 
def contar_violaciones_barras(ruta_resultados):
    """
    Lee Resultados.xlsx (lo genera red_cr.py al terminar) y cuenta
    cuántas barras tienen violación de tensión.
    """
    df = pd.read_excel(ruta_resultados, sheet_name="Barra")
    total_barras   = len(df)
    con_resultado  = int(df["vm_pu"].notna().sum())
    sub_tension    = int((df["vm_pu"] < V_MIN_PU).sum())
    sobre_tension  = int((df["vm_pu"] > V_MAX_PU).sum())
    return {
        "total_barras":      total_barras,
        "con_resultado":     con_resultado,
        "subtension":        sub_tension,
        "sobretension":      sobre_tension,
        "total_violaciones": sub_tension + sobre_tension,
    }
 
 
def evaluar_escenario(escenario):
    """
    Ejecuta red_cr.py para un escenario dado y retorna un diccionario
    con todas las métricas de validación.
    """
    print(f"\n{'='*60}")
    print(f"Ejecutando escenario: {escenario}")
    print(f"{'='*60}")
 
    # 1. Preparar el archivo que red_cr.py va a leer.
    #    Para Max usamos el respaldo; para Min/Med usamos el archivo original
    #    del escenario.
    if escenario == "Max":
        shutil.copy(ARCHIVO_RESPALDO, ARCHIVO_LECTURA)
    else:
        shutil.copy(archivo_fuente(escenario), ARCHIVO_LECTURA)
    print(f"  [1/4] Archivo preparado para escenario {escenario}")
 
    # 2. Correr red_cr.py como subproceso (aislado, fresh Python).
    #    timeout=300s protege contra un eventual loop infinito.
    print(f"  [2/4] Ejecutando red_cr.py ...")
    resultado = subprocess.run(
        ["python", "red_cr.py"],
        capture_output=True,
        text=True,
        timeout=300,
    )
 
    if resultado.returncode != 0:
        print(f"  [!] red_cr.py terminó con código {resultado.returncode}")
        print(f"  stderr: {resultado.stderr[:500]}")
        return {
            "escenario": escenario,
            "convergio": False,
            "error": resultado.stderr[:500],
        }
 
    # 3. Parsear stdout para obtener métricas globales
    metricas = parsear_stdout(resultado.stdout)
    print(f"  [3/4] Métricas extraídas de stdout")
 
    # 4. Leer Resultados.xlsx para contar violaciones por barra, y
    #    guardarlo con un nombre específico del escenario.
    violaciones = contar_violaciones_barras("Resultados.xlsx")
    shutil.copy("Resultados.xlsx", f"Resultados_{escenario}.xlsx")
    print(f"  [4/4] Resultados guardados en Resultados_{escenario}.xlsx")
 
    # Evaluar criterios de aceptación
    viol_V = (metricas["vmin"] < V_MIN_PU) or (metricas["vmax"] > V_MAX_PU)
    viol_carga = (
        (metricas["line_max"]    > LOADING_MAX_PCT) or
        (metricas["trafo_max"]   > LOADING_MAX_PCT) or
        (metricas["trafo3w_max"] > LOADING_MAX_PCT)
    )
 
    return {
        "escenario":              escenario,
        "convergio":              True,
        "vmin_pu":                metricas["vmin"],
        "vmax_pu":                metricas["vmax"],
        "line_max_pct":           metricas["line_max"],
        "trafo2w_max_pct":        metricas["trafo_max"],
        "trafo3w_max_pct":        metricas["trafo3w_max"],
        "total_barras":           violaciones["total_barras"],
        "barras_con_resultado":   violaciones["con_resultado"],
        "barras_subtension":      violaciones["subtension"],
        "barras_sobretension":    violaciones["sobretension"],
        "barras_violacion_V":     violaciones["total_violaciones"],
        "violacion_tension":      viol_V,
        "violacion_cargabilidad": viol_carga,
    }
 
 
# =============================================================================
# Ejecución principal (con respaldo y restauración del Max original)
# =============================================================================
 
def main():
    print("\n" + "#"*60)
    print("# VALIDACIÓN RED DE COSTA RICA — DÍA 2")
    print("# Criterios: V en [0.95, 1.05] pu  |  cargabilidad < 100%")
    print("#"*60)
 
    # -------------------------------------------------------------------------
    # RESPALDO del archivo Max original.
    # Esto es CRÍTICO: red_cr.py lee 'Base_CR_Max_2023-Marzo.xlsx', y ese
    # es el nombre real del archivo Max. Si corremos Min primero, se
    # sobrescribiría el archivo Max original. Por eso respaldamos antes.
    # -------------------------------------------------------------------------
    if not os.path.exists(ARCHIVO_LECTURA):
        raise FileNotFoundError(
            f"No se encuentra {ARCHIVO_LECTURA} en el directorio actual. "
            f"Verifica que estás corriendo el script desde la carpeta del proyecto."
        )
    shutil.copy(ARCHIVO_LECTURA, ARCHIVO_RESPALDO)
    print(f"\n[Setup] Respaldo creado: {ARCHIVO_LECTURA} -> {ARCHIVO_RESPALDO}")
 
    resultados = []
    try:
        for esc in ESCENARIOS:
            try:
                resultados.append(evaluar_escenario(esc))
            except Exception as e:
                print(f"  [!] ERROR en escenario {esc}: {e}")
                resultados.append({
                    "escenario": esc, "convergio": False, "error": str(e)
                })
    finally:
        # ---------------------------------------------------------------------
        # RESTAURAR el archivo Max original, pase lo que pase.
        # Este bloque se ejecuta aunque haya errores en medio del loop.
        # ---------------------------------------------------------------------
        if os.path.exists(ARCHIVO_RESPALDO):
            shutil.copy(ARCHIVO_RESPALDO, ARCHIVO_LECTURA)
            os.remove(ARCHIVO_RESPALDO)
            print(f"\n[Cleanup] Archivo Max original restaurado, respaldo eliminado.")
 
    # Tabla resumen
    df_resumen = pd.DataFrame(resultados)
    print("\n" + "#"*60)
    print("# TABLA RESUMEN")
    print("#"*60)
    print(df_resumen.to_string(index=False))
 
    df_resumen.to_excel("resumen_validacion_dia2.xlsx", index=False)
    print("\nResumen guardado en: resumen_validacion_dia2.xlsx")
 
    # Interpretación automática
    print("\n" + "#"*60)
    print("# INTERPRETACIÓN AUTOMÁTICA")
    print("#"*60)
    for r in resultados:
        if not r.get("convergio"):
            print(f"  [{r['escenario']}] NO convergió — requiere revisión.")
            continue
        print(f"\n  [{r['escenario']}]")
        print(f"    Convergencia: OK")
        print(f"    V: [{r['vmin_pu']:.4f}, {r['vmax_pu']:.4f}] pu "
              f"({'VIOLA' if r['violacion_tension'] else 'OK'})")
        print(f"    Cargabilidad máx: L={r['line_max_pct']:.1f}% "
              f"T2W={r['trafo2w_max_pct']:.1f}% T3W={r['trafo3w_max_pct']:.1f}% "
              f"({'VIOLA' if r['violacion_cargabilidad'] else 'OK'})")
        print(f"    Barras en violación de V: {r['barras_violacion_V']} "
              f"de {r['barras_con_resultado']} con resultado "
              f"({r['barras_subtension']} sub, {r['barras_sobretension']} sobre)")
 
 
if __name__ == "__main__":
    main()