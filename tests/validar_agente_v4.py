"""
validar_agente_v4.py — Validación de la batería sobre la versión final (1.4.1) con el modelo nacional corregido.

Wrapper sobre validar_agente.py que apunta al log de la versión final
(log_bateria_v4.json) y guarda salida con sufijo _v4.

Uso:
    python validar_agente_v4.py
"""

# ---------------------------------------------------------------------------
# Arranque de rutas
# ---------------------------------------------------------------------------
# Este archivo vive en tests/ pero importa modulos de la raiz del proyecto
# (red_cr_loader, tools, agent) y modulos hermanos de tests/ (ground_truth,
# validar_agente). Sin esto, ni "python -m tests.X" ni "python tests/X.py"
# resuelven ambos grupos de imports a la vez.
import os as _os
import sys as _sys
from pathlib import Path as _Path

_RAIZ = _Path(__file__).resolve().parent.parent
# tests/ debe quedar ANTES de la raíz: si en la raíz quedan copias viejas
# de ground_truth.py o gt_loader.py, no deben sombrear a las de tests/.
for _ruta in (str(_RAIZ), str(_RAIZ / "tests")):
    while _ruta in _sys.path:
        _sys.path.remove(_ruta)
    _sys.path.insert(0, _ruta)
_os.chdir(_RAIZ)


from validar_agente import main

if __name__ == "__main__":
    # Escribe directo a su propio archivo. La version anterior escribia a
    # log_validacion.json y despues lo movia, lo que borraba la salida de
    # la validacion pre-mitigacion si ya existia.
    salida = main(
        log_path="logs/log_bateria_v4.json",
        out_dir="logs",
        out_name="log_validacion_v4.json",
    )
    print()
    print("Salida principal: logs/log_validacion_v4.json")
