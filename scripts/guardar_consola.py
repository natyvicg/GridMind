"""
Abre GridMind (main.py) igual que siempre y, además, guarda en un archivo
todo lo que aparece en la consola: lo que imprime el programa y lo que
escribe el usuario.

No modifica ningún archivo del repositorio. Se ejecuta desde la carpeta
GridMind, con el entorno de conda activado:

    python "<ruta de este archivo>" logs/consola_corrida7.txt

Si no se indica nombre, usa logs/consola_FECHA_HORA.txt.
"""
import os
import runpy
import sys
from datetime import datetime


class Duplicador:
    """Escribe en la consola original y en el archivo a la vez."""

    def __init__(self, original, archivo):
        self.original = original
        self.archivo = archivo

    def write(self, texto):
        self.original.write(texto)
        self.archivo.write(texto)
        return len(texto)

    def flush(self):
        self.original.flush()
        self.archivo.flush()

    def fileno(self):
        # Sin descriptor propio: así input() pasa por write/readline y queda registrado.
        raise OSError("sin descriptor")

    def __getattr__(self, nombre):
        return getattr(self.original, nombre)


class EntradaRegistrada:
    """Lee del teclado como siempre y anota cada línea escrita en el archivo."""

    def __init__(self, original, archivo):
        self.original = original
        self.archivo = archivo

    def readline(self, *args):
        linea = self.original.readline(*args)
        self.archivo.write(linea)
        self.archivo.flush()
        return linea

    def fileno(self):
        # Sin descriptor propio: así input() pasa por write/readline y queda registrado.
        raise OSError("sin descriptor")

    def __getattr__(self, nombre):
        return getattr(self.original, nombre)


def main():
    carpeta = os.getcwd()
    if not os.path.isfile(os.path.join(carpeta, "main.py")):
        print("No encuentro main.py en esta carpeta. Primero entrá con cd a la carpeta GridMind.")
        sys.exit(1)

    if len(sys.argv) > 1:
        destino = sys.argv[1]
    else:
        destino = os.path.join("logs", datetime.now().strftime("consola_%Y-%m-%d_%H%M.txt"))
    if os.path.exists(destino):
        print(f"Ya existe {destino}. Elegí otro nombre para no sobrescribirlo.")
        sys.exit(1)
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)

    archivo = open(destino, "w", encoding="utf-8")
    sys.stdout = Duplicador(sys.stdout, archivo)
    sys.stderr = Duplicador(sys.stderr, archivo)
    sys.stdin = EntradaRegistrada(sys.stdin, archivo)

    sys.path.insert(0, carpeta)
    sys.argv = [os.path.join(carpeta, "main.py")]
    try:
        runpy.run_path(os.path.join(carpeta, "main.py"), run_name="__main__")
    finally:
        sys.stdout.flush()
        sys.stdout = sys.stdout.original
        sys.stderr = sys.stderr.original
        archivo.close()
        print(f"\nConsola guardada en: {destino}")


if __name__ == "__main__":
    main()
