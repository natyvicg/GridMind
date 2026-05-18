"""
validar_agente_v2.py — Re-validación tras corrección de umbrales.

Wrapper sobre validar_agente.py que apunta al log post-corrección
(log_bateria_v2.json) y guarda salida con sufijo _v2.

Uso:
    python validar_agente_v2.py
"""

from validar_agente import main

if __name__ == "__main__":
    salida = main(
        log_path="logs/log_bateria_v2.json",
        out_dir="logs",
    )
    # Renombrar las salidas para que no pisen las de la primera validación
    import shutil
    from pathlib import Path
    out = Path("logs")
    if (out / "log_validacion.json").exists():
        shutil.move(out / "log_validacion.json", out / "log_validacion_v2.json")
    print()
    print("Salida principal: logs/log_validacion_v2.json")
