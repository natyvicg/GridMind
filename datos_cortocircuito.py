"""
datos_cortocircuito.py — Capa de datos de cortocircuito para GridMind.

Propósito
---------
El cálculo de corriente de cortocircuito según IEC 60909 requiere la
impedancia de las FUENTES, que el flujo de carga no necesita y por tanto
no siempre está presente en los modelos:

  - Generadores: reactancia subtransitoria (xdss_pu), resistencia
    (rdss_ohm), tensión nominal de máquina (vn_kv), potencia base de
    máquina (sn_mva) y factor de potencia (cos_phi).
  - Red externa: potencia de cortocircuito equivalente (s_sc_max_mva) y
    relación R/X (rx_max).

Este módulo resuelve dos problemas distintos:

1. CORRECCIÓN DE MAPEO EN LA RED CR
   El Excel de la red de Costa Rica proviene de un modelo PSS/E. En la
   hoja 'Generator Data', el registro estándar de PSS/E ubica:
       columna  9  → 'R source (pu)'   = ZR  (impedancia de máquina)
       columna 10  → 'X Source (pu)'   = ZX  (impedancia de máquina)
       columna 11  → 'Rtran (pu)'      = RT  (transformador elevador)
       columna 12  → 'Xtran (pu)'      = XT  (transformador elevador)

   `red_cr.py` (líneas 178-179) lee las columnas 12 y 11 — las del
   transformador elevador, que en este modelo están todas en cero — y
   las asigna a xdss_pu y rdss_pu. La reactancia real de las 108
   máquinas, que sí existe en la columna 10 con valores entre 0.095 y
   0.329 pu, nunca entra al modelo.

   El error es silencioso para el flujo de carga, porque runpp no usa
   xdss_pu. Se vuelve bloqueante en cortocircuito: impedancia cero
   produce corriente infinita y la matriz Ybus se llena de NaN.

   Este módulo remapea la columna correcta SOBRE LA RED YA CONSTRUIDA.
   No modifica `red_cr.py` ni los archivos Excel (regla de integridad
   del proyecto), y verifica la alineación barra por barra antes de
   escribir cualquier valor.

2. DIAGNÓSTICO DE PROCEDENCIA DE DATOS
   Las redes IEEE de `pandapower.networks` son casos de prueba de flujo
   de carga (IEEE Common Data Format / MATPOWER) y no incluyen ningún
   parámetro de cortocircuito: sn_mva viene en NaN y las columnas
   xdss_pu y s_sc_max_mva no existen. `diagnosticar()` detecta esa
   ausencia y nombra exactamente qué falta, para que la herramienta
   informe en vez de inventar. `aplicar_parametros_tipicos()` permite
   calcular de todas formas, pero el resultado queda rotulado como
   basado en supuestos declarados y no en el modelo.

Supuestos declarados (documentar en el TFG)
-------------------------------------------
  - R de máquina: el modelo CR trae 'R source (pu)' en cero para las 108
    unidades. Se asume R = X / (X/R) con X/R = 20, valor típico para
    máquinas sincrónicas de transmisión.
  - Tensión nominal de máquina: se toma la tensión nominal de la barra
    de conexión, al no haber un campo explícito en el Excel.
  - Interconexiones: `red_cr.py` modela las conexiones con Nicaragua y
    Panamá como cinco fuentes ideales (ext_grid) en barras que el modelo
    PSS/E original clasifica como barras de carga. Una fuente ideal
    tiene impedancia nula, lo que es inadmisible en cortocircuito, por
    lo que su potencia de cortocircuito se expone como PARÁMETRO. El
    análisis de sensibilidad muestra que su efecto es local: variar el
    supuesto de 500 a 20 000 MVA mueve la mediana de Icc del resto de la
    red un 3.1 %.

Uso
---
    from datos_cortocircuito import preparar_red_cr, diagnosticar
    net, informe = preparar_red_cr(net, "Min")
"""

import math
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

HOJA_GENERADORES = "Generator Data"
HOJA_BARRAS = "Bus Data"

# Columnas de la hoja 'Bus Data' (formato PSS/E).
COL_BUS_BARRA = 0
COL_BUS_NOMBRE = 1

# Índices de columna en la hoja 'Generator Data' (formato PSS/E).
COL_BARRA = 0
COL_MBASE = 8
COL_R_SOURCE = 9
COL_X_SOURCE = 10

# Archivos de la red CR. Se trabaja SIEMPRE desde los backups permanentes
# creados por red_cr_loader.py; los originales son solo respaldo final.
CR_BACKUPS = {
    "Min": "_Backup_Min_2023-Marzo.xlsx",
    "Med": "_Backup_Med_2023-Marzo.xlsx",
    "Max": "_Backup_Max_2023-Marzo.xlsx",
}
CR_ORIGINALES = {
    "Min": "Base_CR_Min_2023-Marzo.xlsx",
    "Med": "Base_CR_Med_2023-Marzo.xlsx",
    "Max": "Base_CR_Max_2023-Marzo.xlsx",
}

# Supuestos por defecto (todos documentados y sobreescribibles).
X_R_MAQUINA = 20.0                  # relación X/R asumida para R de máquina
COS_PHI_MAQUINA = 0.85              # factor de potencia nominal asumido
SSC_INTERCONEXION_MVA = 2000.0      # potencia de cortocircuito de ext_grid
RX_INTERCONEXION = 0.1              # relación R/X de la red externa
# Temperatura final de conductor para el caso mínimo. IEC 60909 corrige la
# resistencia de las líneas a la temperatura que alcanzan al final del
# cortocircuito, R = R20*(1 + 0.004*(theta_e - 20)), y pandapower exige el
# dato (net.line.endtemp_degree) cuando case="min". Ningún modelo lo trae.
ENDTEMP_MIN_DEGREE = 80.0

# Parámetros típicos para redes sin datos (solo con rótulo de supuesto).
XDSS_TIPICO_PU = 0.20               # reactancia subtransitoria típica
SN_MVA_TIPICO = 100.0               # potencia base de máquina por defecto

PROYECTO_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Lectura de impedancias desde el Excel
# ---------------------------------------------------------------------------

def _ruta_excel_cr(escenario):
    """
    Devuelve la ruta del Excel a leer para el escenario indicado.
    Prioriza el backup permanente; si no existe, usa el original.
    Nunca escribe sobre ninguno de los dos.
    """
    if escenario not in CR_BACKUPS:
        raise ValueError(
            "Escenario inválido: {!r}. Usar uno de: {}".format(
                escenario, list(CR_BACKUPS)
            )
        )

    backup = PROYECTO_DIR / CR_BACKUPS[escenario]
    if backup.exists():
        return backup

    original = PROYECTO_DIR / CR_ORIGINALES[escenario]
    if original.exists():
        return original

    raise FileNotFoundError(
        "No se encontró ni {} ni {} en {}.".format(
            CR_BACKUPS[escenario], CR_ORIGINALES[escenario], PROYECTO_DIR
        )
    )


def _leer_impedancias_cr(escenario):
    """
    Lee barra, Mbase, R source y X source de la hoja de generadores.
    Devuelve un DataFrame con columnas: barra, mbase_mva, r_source_pu,
    x_source_pu, en el mismo orden en que aparecen en el Excel.
    """
    ruta = _ruta_excel_cr(escenario)
    crudo = pd.read_excel(ruta, sheet_name=HOJA_GENERADORES, header=None)

    # La fila 0 son encabezados; los datos empiezan en la fila 1.
    datos = crudo.iloc[1:, :]

    df = pd.DataFrame({
        "barra": pd.to_numeric(datos.iloc[:, COL_BARRA], errors="coerce"),
        "mbase_mva": pd.to_numeric(datos.iloc[:, COL_MBASE], errors="coerce"),
        "r_source_pu": pd.to_numeric(datos.iloc[:, COL_R_SOURCE], errors="coerce"),
        "x_source_pu": pd.to_numeric(datos.iloc[:, COL_X_SOURCE], errors="coerce"),
    }).dropna(subset=["barra"]).reset_index(drop=True)

    df["barra"] = df["barra"].astype(int)
    return df, ruta.name


def mapa_nombres_cr(escenario):
    """
    Devuelve {índice de barra: nombre de subestación} leyendo la hoja
    'Bus Data' del Excel.

    `red_cr.py` crea las barras con el número de barra como nombre, así
    que la red construida no conserva los nombres de subestación (por
    ejemplo 'REV-U2' para la barra 58521). Este mapa permite presentar
    resultados con el nombre real, que es mucho más informativo en un
    informe técnico que un índice numérico.

    Es solo para presentación: no modifica la red ni afecta ningún
    cálculo. Si el Excel no está disponible, devuelve un dict vacío.
    """
    try:
        ruta = _ruta_excel_cr(escenario)
        crudo = pd.read_excel(ruta, sheet_name=HOJA_BARRAS, header=None)
    except (FileNotFoundError, ValueError, KeyError):
        return {}

    mapa = {}
    for _, fila in crudo.iloc[1:, :].iterrows():
        try:
            barra = int(fila.iloc[COL_BUS_BARRA])
        except (TypeError, ValueError):
            continue
        nombre = fila.iloc[COL_BUS_NOMBRE]
        if nombre is None or (isinstance(nombre, float) and math.isnan(nombre)):
            continue
        limpio = str(nombre).strip().strip("'").strip()
        if limpio:
            mapa[barra] = limpio
    return mapa


# ---------------------------------------------------------------------------
# Diagnóstico de procedencia de datos
# ---------------------------------------------------------------------------

def diagnosticar(net):
    """
    Determina si la red tiene los datos que IEC 60909 requiere.

    Devuelve un dict con:
        apta      bool  — True si se puede calcular con datos del modelo
        faltantes list  — descripción de cada parámetro ausente
    """
    faltantes = []

    # --- Red externa ---
    if len(net.ext_grid):
        if "s_sc_max_mva" not in net.ext_grid.columns:
            faltantes.append(
                "potencia de cortocircuito de la red externa (s_sc_max_mva) "
                "para {} alimentador(es) externo(s)".format(len(net.ext_grid))
            )
        elif net.ext_grid["s_sc_max_mva"].isna().any():
            faltantes.append(
                "potencia de cortocircuito de la red externa (s_sc_max_mva): "
                "{} de {} alimentadores sin valor".format(
                    int(net.ext_grid["s_sc_max_mva"].isna().sum()),
                    len(net.ext_grid),
                )
            )

    # --- Generadores ---
    if len(net.gen):
        if "xdss_pu" not in net.gen.columns:
            faltantes.append(
                "reactancia subtransitoria de generadores (xdss_pu) para "
                "{} máquina(s)".format(len(net.gen))
            )
        else:
            x = pd.to_numeric(net.gen["xdss_pu"], errors="coerce")
            sin_dato = int((x.isna() | (x <= 0)).sum())
            if sin_dato:
                faltantes.append(
                    "reactancia subtransitoria de generadores (xdss_pu): "
                    "{} de {} máquinas en cero o sin valor".format(
                        sin_dato, len(net.gen)
                    )
                )

        if "sn_mva" not in net.gen.columns or net.gen["sn_mva"].isna().any():
            n_sin = (
                len(net.gen)
                if "sn_mva" not in net.gen.columns
                else int(net.gen["sn_mva"].isna().sum())
            )
            faltantes.append(
                "potencia base de máquina (sn_mva): {} de {} máquinas "
                "sin valor".format(n_sin, len(net.gen))
            )

        if "vn_kv" not in net.gen.columns or net.gen["vn_kv"].isna().all():
            faltantes.append(
                "tensión nominal de máquina (vn_kv) para "
                "{} máquina(s)".format(len(net.gen))
            )

        if "cos_phi" not in net.gen.columns or net.gen["cos_phi"].isna().all():
            faltantes.append(
                "factor de potencia nominal de máquina (cos_phi) para "
                "{} máquina(s)".format(len(net.gen))
            )

    return {"apta": len(faltantes) == 0, "faltantes": faltantes}


# ---------------------------------------------------------------------------
# Preparación de la red CR (datos reales del modelo PSS/E)
# ---------------------------------------------------------------------------

def preparar_red_cr(
    net,
    escenario,
    s_sc_interconexion_mva=SSC_INTERCONEXION_MVA,
    x_r_maquina=X_R_MAQUINA,
    cos_phi=COS_PHI_MAQUINA,
    rx_interconexion=RX_INTERCONEXION,
):
    """
    Completa los datos de cortocircuito de la red CR sobre la red ya
    construida, sin tocar red_cr.py ni los Excel.

    La reactancia de máquina se remapea desde la columna 'X Source (pu)'
    del Excel, que es la impedancia de máquina en el formato PSS/E. Se
    verifica que el orden de net.gen coincida barra por barra con el
    orden del Excel antes de escribir; si no coincide, se lanza
    RuntimeError en vez de escribir datos desalineados.

    Devuelve (net, informe).
    """
    imp, archivo = _leer_impedancias_cr(escenario)

    if len(imp) != len(net.gen):
        raise RuntimeError(
            "Desalineación: el Excel tiene {} generadores y la red {}. "
            "No se remapea nada.".format(len(imp), len(net.gen))
        )

    barras_net = [int(b) for b in net.gen["bus"].tolist()]
    barras_xls = imp["barra"].tolist()
    if barras_net != barras_xls:
        n_dif = sum(1 for a, b in zip(barras_net, barras_xls) if a != b)
        raise RuntimeError(
            "Desalineación barra por barra entre net.gen y el Excel "
            "({} discrepancias). No se remapea nada.".format(n_dif)
        )

    # --- Reactancia de máquina: valor real del modelo ---
    x_pu = imp["x_source_pu"].astype(float).values
    net.gen["xdss_pu"] = x_pu

    # --- Resistencia de máquina: supuesto declarado ---
    # El modelo trae 'R source (pu)' en cero para las 108 unidades.
    r_source = imp["r_source_pu"].astype(float).values
    r_del_modelo = bool((r_source > 0).any())
    r_pu = r_source if r_del_modelo else x_pu / float(x_r_maquina)
    net.gen["rdss_pu"] = r_pu

    # --- Tensión nominal de máquina: tensión de la barra de conexión ---
    net.gen["vn_kv"] = net.bus.loc[net.gen["bus"], "vn_kv"].values

    # --- Potencia base de máquina: Mbase del Excel ---
    net.gen["sn_mva"] = imp["mbase_mva"].astype(float).values

    # pandapower espera la resistencia de máquina en ohmios.
    net.gen["rdss_ohm"] = (
        net.gen["rdss_pu"] * net.gen["vn_kv"] ** 2 / net.gen["sn_mva"]
    )

    net.gen["cos_phi"] = float(cos_phi)
    net.gen["pg_percent"] = 0.0

    # --- Red externa: parámetro declarado ---
    net.ext_grid["s_sc_max_mva"] = float(s_sc_interconexion_mva)
    net.ext_grid["rx_max"] = float(rx_interconexion)

    nombres_ext = [str(n).strip() for n in net.ext_grid.get("name", [])]

    informe = {
        "norma": "IEC 60909",
        "escenario": escenario,
        "archivo_datos": archivo,
        "nombres_barras": mapa_nombres_cr(escenario),
        "alineacion_verificada": True,
        "n_maquinas": int(len(net.gen)),
        "n_maquinas_en_servicio": int(net.gen["in_service"].sum()),
        "xdss_pu_min": round(float(x_pu.min()), 5),
        "xdss_pu_max": round(float(x_pu.max()), 5),
        "fuente_xdss": (
            "modelo PSS/E — hoja '{}', columna 'X Source (pu)' "
            "(impedancia de máquina, registro ZX)".format(HOJA_GENERADORES)
        ),
        "correccion_de_mapeo": (
            "red_cr.py asigna a xdss_pu la columna 'Xtran (pu)' "
            "(transformador elevador, cero en este modelo). Se remapeó "
            "desde 'X Source (pu)', que es la impedancia de máquina."
        ),
        "supuestos": [
            "R de máquina: 'R source (pu)' viene en cero en el modelo; se "
            "asume R = X / {:.0f}.".format(x_r_maquina)
            if not r_del_modelo else
            "R de máquina: tomada del modelo ('R source (pu)').",
            "Tensión nominal de máquina: se usa la tensión nominal de la "
            "barra de conexión (el Excel no trae campo explícito).",
            "Factor de potencia nominal de máquina: cos_phi = {}.".format(cos_phi),
            "Interconexiones ({}): red_cr.py las modela como fuentes "
            "ideales; se les asigna S_cc = {:.0f} MVA y R/X = {} como "
            "parámetro declarado, no como dato del modelo.".format(
                ", ".join(nombres_ext) if nombres_ext else len(net.ext_grid),
                s_sc_interconexion_mva,
                rx_interconexion,
            ),
        ],
    }

    return net, informe


# ---------------------------------------------------------------------------
# Parámetros típicos para redes sin datos de cortocircuito
# ---------------------------------------------------------------------------

def aplicar_parametros_tipicos(
    net,
    xdss_pu=XDSS_TIPICO_PU,
    sn_mva=SN_MVA_TIPICO,
    s_sc_mva=SSC_INTERCONEXION_MVA,
    x_r_maquina=X_R_MAQUINA,
    cos_phi=COS_PHI_MAQUINA,
    rx_red_externa=RX_INTERCONEXION,
):
    """
    Rellena los parámetros de cortocircuito ausentes con valores típicos
    de literatura. El resultado NO representa el modelo: se usa solo
    cuando el usuario lo solicita explícitamente y siempre queda
    rotulado como supuesto.

    Devuelve (net, informe).
    """
    supuestos = []

    if len(net.gen):
        net.gen["xdss_pu"] = float(xdss_pu)
        net.gen["rdss_pu"] = float(xdss_pu) / float(x_r_maquina)
        net.gen["vn_kv"] = net.bus.loc[net.gen["bus"], "vn_kv"].values

        sn = pd.to_numeric(net.gen.get("sn_mva"), errors="coerce")
        if sn is None or sn.isna().all():
            net.gen["sn_mva"] = float(sn_mva)
            supuestos.append(
                "Potencia base de máquina: {} MVA (el modelo no la "
                "trae).".format(sn_mva)
            )
        else:
            net.gen["sn_mva"] = sn.fillna(float(sn_mva))

        net.gen["rdss_ohm"] = (
            net.gen["rdss_pu"] * net.gen["vn_kv"] ** 2 / net.gen["sn_mva"]
        )
        net.gen["cos_phi"] = float(cos_phi)
        net.gen["pg_percent"] = 0.0

        supuestos.append(
            "Reactancia subtransitoria: {} pu para las {} máquinas, valor "
            "típico de máquina sincrónica.".format(xdss_pu, len(net.gen))
        )
        supuestos.append(
            "R de máquina: R = X / {:.0f}.".format(x_r_maquina)
        )
        supuestos.append(
            "Tensión nominal de máquina: tensión nominal de la barra de "
            "conexión."
        )
        supuestos.append(
            "Factor de potencia nominal de máquina: {}.".format(cos_phi)
        )

    if len(net.ext_grid):
        net.ext_grid["s_sc_max_mva"] = float(s_sc_mva)
        net.ext_grid["rx_max"] = float(rx_red_externa)
        supuestos.append(
            "Potencia de cortocircuito de la red externa: {:.0f} MVA, "
            "R/X = {}.".format(s_sc_mva, rx_red_externa)
        )

    informe = {
        "norma": "IEC 60909",
        "fuente_xdss": "parámetros típicos de literatura (NO del modelo)",
        "supuestos": supuestos,
    }

    return net, informe


# ---------------------------------------------------------------------------
# Auto-test: python datos_cortocircuito.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Impedancias de máquina en el Excel de la red CR")
    print("=" * 70)
    for esc in ("Min", "Med", "Max"):
        try:
            imp, archivo = _leer_impedancias_cr(esc)
        except FileNotFoundError as e:
            print("  {}: {}".format(esc, e))
            continue
        x = imp["x_source_pu"]
        r = imp["r_source_pu"]
        print(
            "  {}  ({}): {} máquinas | X source {:.4f} a {:.4f} pu | "
            "R source distinto de cero: {}".format(
                esc, archivo, len(imp), x.min(), x.max(), int((r > 0).sum())
            )
        )
    print()
    print("Comparación con lo que red_cr.py asigna hoy a xdss_pu:")
    print("  lee la columna 12 ('Xtran (pu)'), que está en cero para todas")
    print("  las unidades. La impedancia real está en la columna 10")
    print("  ('X Source (pu)'), que es la que remapea este módulo.")
