"""
red_cr_loader.py — Adaptador de red_cr.py para GridMind.

Diseño (NO toca red_cr.py ni los Excel originales)
----------------------------------------------------
red_cr.py tiene hardcoded en su línea 17 el nombre 'Base_CR_Max_2023-Marzo.xlsx'.
Para cargar otros escenarios sin modificar ese archivo, este loader:

  1. En la primera ejecución, crea copias permanentes de los 3 Excel
     originales (Min, Med, Max) en archivos _Backup_*.  Estas copias
     se crean UNA sola vez y nunca se sobreescriben.

  2. Para cada carga, trabaja SIEMPRE desde los backups (nunca desde
     los originales).

  3. Crea un directorio temporal, copia ahí el backup del escenario
     solicitado con el nombre que red_cr.py espera, copia red_cr.py,
     ejecuta desde ahí, y limpia al terminar.

Resultado: los 3 archivos Excel originales NUNCA se modifican.
Los backups se crean una vez y tampoco se sobreescriben.

Uso
---
    from red_cr_loader import cargar_red_cr
    net = cargar_red_cr("Min")   # también: "Med" o "Max"
"""

import io
import os
import shutil
import sys
import tempfile
import runpy
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Mapa: escenario -> archivo Excel original (solo se lee 1 vez para backup).
CR_ORIGINALES = {
    "Min": "Base_CR_Min_2023-Marzo.xlsx",
    "Med": "Base_CR_Med_2023-Marzo.xlsx",
    "Max": "Base_CR_Max_2023-Marzo.xlsx",
}

# Mapa: escenario -> copia permanente de seguridad (fuente de trabajo).
CR_BACKUPS = {
    "Min": "_Backup_Min_2023-Marzo.xlsx",
    "Med": "_Backup_Med_2023-Marzo.xlsx",
    "Max": "_Backup_Max_2023-Marzo.xlsx",
}

# Nombre que red_cr.py tiene hardcoded en su pd.read_excel(...) (línea 17).
NOMBRE_HARDCODED = "Base_CR_Max_2023-Marzo.xlsx"

# Cache en memoria: {escenario: net}
_CACHE = {}


# ---------------------------------------------------------------------------
# Gestión de backups permanentes
# ---------------------------------------------------------------------------

def _asegurar_backups(proyecto_dir):
    """
    Verifica que existan los 3 backups permanentes. Si alguno falta,
    lo crea desde el archivo original correspondiente.

    Los backups que ya existen NUNCA se sobreescriben — son la fuente
    de verdad inmutable.
    """
    for escenario in CR_ORIGINALES:
        backup = proyecto_dir / CR_BACKUPS[escenario]
        original = proyecto_dir / CR_ORIGINALES[escenario]

        if backup.exists():
            continue

        if not original.exists():
            raise FileNotFoundError(
                "No se encontró el archivo original {} en {}. "
                "No se puede crear el backup.".format(
                    CR_ORIGINALES[escenario], proyecto_dir
                )
            )

        shutil.copyfile(original, backup)


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
    if escenario not in CR_ORIGINALES:
        raise ValueError(
            "Escenario inválido: {!r}. Usar uno de: {}".format(
                escenario, list(CR_ORIGINALES)
            )
        )

    if not forzar_recarga and escenario in _CACHE:
        return _CACHE[escenario]

    # Directorio donde viven los archivos del proyecto.
    proyecto_dir = Path(__file__).resolve().parent

    red_cr_path = proyecto_dir / "red_cr.py"
    if not red_cr_path.exists():
        raise FileNotFoundError(
            "No se encontró red_cr.py en {}.".format(proyecto_dir)
        )

    # Crear backups si es la primera vez (no sobreescribe los existentes).
    _asegurar_backups(proyecto_dir)

    # Siempre trabajar desde el backup, nunca desde el original.
    fuente = proyecto_dir / CR_BACKUPS[escenario]
    if not fuente.exists():
        raise FileNotFoundError(
            "No se encontró el backup {} en {}.".format(
                CR_BACKUPS[escenario], proyecto_dir
            )
        )

    # Crear directorio temporal, copiar lo necesario, ejecutar desde ahí.
    tmpdir = tempfile.mkdtemp(prefix="gridmind_cr_")
    cwd_original = os.getcwd()

    try:
        # 1. Copiar el backup del escenario con el nombre hardcoded.
        shutil.copyfile(fuente, os.path.join(tmpdir, NOMBRE_HARDCODED))

        # 2. Copiar red_cr.py al directorio temporal.
        shutil.copyfile(red_cr_path, os.path.join(tmpdir, "red_cr.py"))

        # 3. Cambiar al directorio temporal.
        os.chdir(tmpdir)

        # 4. Ejecutar red_cr.py opcionalmente silenciando su salida.
        if silenciar:
            stdout_orig = sys.stdout
            sys.stdout = io.StringIO()
        try:
            ns = runpy.run_path(os.path.join(tmpdir, "red_cr.py"))
        finally:
            if silenciar:
                sys.stdout = stdout_orig

        red = ns["Red_CR1"]
        _CACHE[escenario] = red
        return red

    finally:
        # 5. Siempre volver al directorio original y limpiar el temporal.
        os.chdir(cwd_original)
        shutil.rmtree(tmpdir, ignore_errors=True)


def limpiar_cache():
    """Vacía el cache en memoria. No toca archivos."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Auto-test cuando se ejecuta directamente: python red_cr_loader.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Test rápido: cargando los 3 escenarios CR")
    print("(Backups permanentes + directorio temporal)")
    print("=" * 60)

    proyecto_dir = Path(__file__).resolve().parent
    for esc in ("Min", "Med", "Max"):
        backup = proyecto_dir / CR_BACKUPS[esc]
        estado = "existe" if backup.exists() else "se creará ahora"
        print(f"  Backup {esc}: {backup.name} ({estado})")

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
    print("Los archivos originales NO fueron modificados.")
    print("Los backups permanentes están en disco.")
    print("=" * 60)

