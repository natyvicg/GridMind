"""
main.py — Interfaz CLI interactiva de GridMind.

Punto de entrada para hablar con el agente desde la terminal. Lee la
API key desde .env, presenta un prompt interactivo y despacha cada
consulta al loop ReAct de agent.py.

USO:
    python main.py

COMANDOS ESPECIALES:
    /reset   Limpia la red cargada (empezás de cero)
    /salir   Termina la sesión

REQUISITOS:
    - Archivo .env en la misma carpeta con: ANTHROPIC_API_KEY=sk-ant-...
    - Librerías: pandapower, anthropic, python-dotenv
"""

import os
import sys
from dotenv import load_dotenv

# Cargar la API key ANTES de importar el cliente Anthropic
load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("\n❌ ERROR: no se encontró ANTHROPIC_API_KEY en .env")
    print("   Revisá que el archivo .env esté en la misma carpeta y tenga:")
    print("   ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

from agent import run_react_loop
from tools import reset_network


BANNER = """
╔══════════════════════════════════════════════════════╗
║           GridMind - Agente Eléctrico                ║
║   Claude + PandaPower para análisis de red           ║
╠══════════════════════════════════════════════════════╣
║  Escribí tu consulta en lenguaje natural.            ║
║  El agente razona y usa PandaPower para responder.   ║
╚══════════════════════════════════════════════════════╝
Comandos: /reset (reiniciar red)  |  /salir (terminar)
"""


def main():
    print(BANNER)

    while True:
        try:
            user_input = input("\n👤 Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Hasta luego.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/salir", "/exit", "/quit"):
            print("\n👋 Hasta luego.")
            break

        if user_input.lower() == "/reset":
            reset_network()
            print("🔄 Red descargada. La próxima consulta cargará la red desde cero.")
            continue

        # Cada consulta es independiente: el loop ReAct maneja internamente
        # las múltiples iteraciones (razonar → tool_use → resultado → ...).
        # El estado de la red persiste entre consultas vía _STATE en tools.py,
        # así que consultas sucesivas sobre la misma red son eficientes.
        try:
            print("\n🤖 GridMind está pensando...\n")
            result = run_react_loop(user_query=user_input, verbose=True)
            print(f"\n🤖 GridMind: {result['final_text']}")
            print(f"\n   [{result['iterations']} iteraciones, "
                  f"{result['usage']['input_tokens']}+{result['usage']['output_tokens']} tokens]")
        except Exception as e:
            print(f"\n❌ Error al procesar: {e}")
            print("   Probá con /reset si el problema persiste.")


if __name__ == "__main__":
    main()
