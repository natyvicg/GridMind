"""
red_cr_loader.py — Adaptador de red_cr.py para GridMind.

Diseño (NO toca red_cr.py)
---------------------------
red_cr.py tiene hardcoded en su línea 17 el nombre 'Base_CR_Max_2023-Marzo.xlsx'.
Para cargar otros escenarios, este loader necesita escribir datos sobre ese
nombre. Eso pone en riesgo el archivo Max original.

Estrategia para preservar SIEMPRE el archivo Max original:

  1. Al primer uso, se crea un backup permanente del archivo Max original
     en _Backup_Max_2023-Marzo.xlsx. Este backup se mantiene en disco entre
     sesiones — es la "fuente de verdad" del Max original.

  2. Antes de cargar un escenario, se verifica que el archivo de trabajo
     'Base_CR_Max_2023-Marzo.xlsx' coincida con el backup. Si no coincide
     (porque un cierre anormal previo lo dejó "sucio" con datos de otro
     escenario), se restaura automáticamente desde el backup.

  3. Para cargar Min/Med, se copia el archivo del escenario al nombre que
     red_cr.py espera. Para cargar Max, se copia desde el BACKUP (no desde
     el archivo de trabajo, que pudo haberse contaminado en pasos previos).

  4. Al cerrar el script (incluso por excepción), un handler atexit restaura
     el archivo de trabajo desde el backup, devolviendo el directorio al
     estado limpio inicial.

Resultado: red_cr.py jamás se modifica, y los 3 archivos Excel originales
quedan preservados al cierre de cada sesión, sea cual sea el camino de
salida.

Uso
---
    from red_cr_loader import cargar_red_cr
    net = cargar_red_cr("Min")   # también: "Med" o "Max"
"""

import atexit
import filecmp
import io
import shutil
import sys
import runpy
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Mapa: escenario -> archivo Excel real (NUNCA se modifica).
CR_FUENTES = {
    "Min": "Base_CR_Min_2023-Marzo.xlsx",
    "Med": "Base_CR_Med_2023-Marzo.xlsx",
    "Max": "Base_CR_Max_2023-Marzo.xlsx",
}

# Nombre que red_cr.py tiene hardcoded en su pd.read_excel(...) (línea 17).
# Este archivo es el "destino de trabajo": el loader le escribe datos
# distintos según el escenario solicitado, y atexit lo restaura al final.
ARCHIVO_TRABAJO = "Base_CR_Max_2023-Marzo.xlsx"

# Backup permanente del archivo Max original. Se crea la primera vez y
# permanece en disco entre sesiones como fuente de verdad de Max.
BACKUP_MAX = "_Backup_Max_2023-Marzo.xlsx"

# Cache en memoria: {escenario: net}
_CACHE = {}


# ---------------------------------------------------------------------------
# Manejo del backup y restauración
# ---------------------------------------------------------------------------

def _asegurar_backup_y_estado_limpio():
    """
    Garantiza que el backup del Max original existe y que el archivo de
    trabajo está en estado consistente con él.

    Flujo:
      - Si no existe el backup: crearlo desde el archivo de trabajo actual
        (esto SOLO es válido si el archivo de trabajo aún tiene los datos
        originales de Max). Se asume que la primera vez que el loader corre,
        el archivo está limpio.
      - Si existe el backup pero el archivo de trabajo no coincide con él:
        restaurar el archivo de trabajo desde el backup. Esto cubre el caso
        de un cierre anormal previo que dejó el archivo "sucio".
    """
    trabajo = Path(ARCHIVO_TRABAJO)
    backup = Path(BACKUP_MAX)

    if not trabajo.exists():
        raise FileNotFoundError(
            "No se encontró {} en {}. Restáurelo antes de continuar.".format(
                ARCHIVO_TRABAJO, Path.cwd()
            )
        )

    if not backup.exists():
        # Primera vez: crear backup. Asume que el archivo de trabajo
        # contiene los datos originales de Max.
        shutil.copyfile(trabajo, backup)
        return

    # Backup existe. Verificar coincidencia byte a byte.
    if not filecmp.cmp(trabajo, backup, shallow=False):
        # Archivo "sucio": restaurar desde backup.
        shutil.copyfile(backup, trabajo)


def _restaurar_al_cerrar():
    """
    Handler atexit: al cerrar el script, restaura el archivo de trabajo
    desde el backup. Idempotente y silencioso.
    """
    try:
        backup = Path(BACKUP_MAX)
        trabajo = Path(ARCHIVO_TRABAJO)
        if backup.exists() and trabajo.exists():
            if not filecmp.cmp(trabajo, backup, shallow=False):
                shutil.copyfile(backup, trabajo)
    except Exception:
        # No propagar errores en atexit: el script ya está terminando.
        pass


atexit.register(_restaurar_al_cerrar)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def cargar_red_cr(escenario, forzar_recarga=False, silenciar=True):
    """
    Carga la red eléctrica de Costa Rica para el escenario solicitado.

    Parámetros
    ----------
    escenario : str
        Uno de "Min", "Med", "Max".
    forzar_recarga : bool
        Si True, ignora el cache y reconstruye desde cero.
    silenciar : bool
        Si True, suprime el stdout que red_cr.py emite durante la
        construcción. Por defecto True.

    Retorna
    -------
    pandapower.Network
        Red Red_CR1 con flujo de potencia ya corrido por red_cr.py.
    """
    if escenario not in CR_FUENTES:
        raise ValueError(
            "Escenario inválido: {!r}. Usar uno de: {}".format(
                escenario, list(CR_FUENTES)
            )
        )

    if not forzar_recarga and escenario in _CACHE:
        return _CACHE[escenario]

    if not Path("red_cr.py").exists():
        raise FileNotFoundError(
            "No se encontró red_cr.py en {}.".format(Path.cwd())
        )

    # Garantizar backup y limpiar el archivo de trabajo si quedó "sucio"
    # de una sesión previa.
    _asegurar_backup_y_estado_limpio()

    # Determinar la fuente desde la que copiar.
    # Para Min/Med: el archivo Excel original (nunca es destino, está a salvo).
    # Para Max:     el backup permanente (que sí preserva los datos originales
    #               de Max aunque el archivo de trabajo se haya contaminado).
    if escenario == "Max":
        fuente = Path(BACKUP_MAX)
    else:
        fuente = Path(CR_FUENTES[escenario])

    if not fuente.exists():
        raise FileNotFoundError(
            "No se encontró {} en {}.".format(fuente, Path.cwd())
        )

    # Copiar al archivo de trabajo. Si fuente == destino (puede pasar la
    # primera vez con Max si el backup todavía no existía y se creó recién
    # apuntando al mismo archivo), saltar la copia.
    if fuente.resolve() != Path(ARCHIVO_TRABAJO).resolve():
        shutil.copyfile(fuente, ARCHIVO_TRABAJO)

    # Ejecutar red_cr.py opcionalmente silenciando su salida.
    if silenciar:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
    try:
        ns = runpy.run_path("red_cr.py")
    finally:
        if silenciar:
            sys.stdout = stdout_orig

    red = ns["Red_CR1"]
    _CACHE[escenario] = red
    return red


def limpiar_cache():
    """Vacía el cache en memoria. No toca archivos."""
    _CACHE.clear()


def restaurar_max_manual():
    """Función pública por si el usuario quiere forzar restauración."""
    if Path(BACKUP_MAX).exists():
        shutil.copyfile(BACKUP_MAX, ARCHIVO_TRABAJO)
        return True
    return False


# ---------------------------------------------------------------------------
# Auto-test cuando se ejecuta directamente: python red_cr_loader.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Test rápido: cargando los 3 escenarios CR")
    print("=" * 60)

    # Mostrar si se va a crear el backup en este run.
    if not Path(BACKUP_MAX).exists():
        print("\n[setup] Primera ejecución: se creará backup permanente "
              "del archivo Max original en {}".format(BACKUP_MAX))
    else:
        print("\n[setup] Backup ya existe: {}".format(BACKUP_MAX))

    for esc in ("Min", "Med", "Max"):
        print(f"\n[{esc}] Cargando...")
        net = cargar_red_cr(esc)
        n_bus = len(net.bus)
        n_line = len(net.line)
        n_trafo = len(net.trafo) + len(net.trafo3w)
        n_load = len(net.load)
        n_gen = len(net.gen)
        converged = bool(getattr(net, "converged", False))
        print(f"  Barras: {n_bus} | Líneas: {n_line} | Trafos: {n_trafo}")
        print(f"  Cargas: {n_load} | Generadores: {n_gen}")
        print(f"  Convergencia: {converged}")
        if not net.res_bus.empty:
            print(f"  Vmin: {net.res_bus.vm_pu.min():.4f} pu | "
                  f"Vmax: {net.res_bus.vm_pu.max():.4f} pu")

    print("\n" + "=" * 60)
    print("Cache poblado:", list(_CACHE.keys()))
    print("Los 3 escenarios deben dar Vmin/Vmax DISTINTOS entre sí.")
    print("Al cerrar este script, el archivo de trabajo se restaurará")
    print("automáticamente desde {}.".format(BACKUP_MAX))
    print("=" * 60)
