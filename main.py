"""
main.py — Interfaz CLI interactiva de GridMind.

Punto de entrada para hablar con el agente desde la terminal. Lee la
API key desde .env, presenta un prompt interactivo y despacha cada
consulta al loop ReAct de agent.py.

USO:
    python main.py

COMANDOS ESPECIALES:
    /ayuda      Lista de comandos disponibles
    /redes      Muestra las redes disponibles
    /guardar    Exporta la sesión completa a un archivo Markdown
    /historial  Muestra las consultas hechas en esta sesión
    /reset      Limpia la red cargada (empezás de cero)
    /salir      Termina la sesión

REQUISITOS:
    - Archivo .env en la misma carpeta con: ANTHROPIC_API_KEY=sk-ant-...
    - Librerías: pandapower, anthropic, python-dotenv
"""

import os
import sys
import re
import time
from datetime import datetime
from pathlib import Path
from tools import AVAILABLE_NETWORKS

from dotenv import load_dotenv

# Cargar la API key ANTES de importar el cliente Anthropic
load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("\n  ERROR: no se encontró ANTHROPIC_API_KEY en .env")
    print("  Revisá que el archivo .env esté en la misma carpeta y tenga:")
    print("  ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

from agent import run_react_loop
from tools import reset_network


# ═════════════════════════════════════════════════════════════════════════
# Configuración
# ═════════════════════════════════════════════════════════════════════════

VERSION = "1.1.0"

# Precios Claude Sonnet (USD por millón de tokens)
PRECIO_INPUT  = 3.00
PRECIO_OUTPUT = 15.00

LOGS_DIR = Path("logs")

def _box_line(text, width=54):
    """Centra una línea dentro del marco."""
    pad_total = width - len(text)
    pad_left = pad_total // 2
    pad_right = pad_total - pad_left
    return f"║  {' ' * pad_left}{text}{' ' * pad_right}║"

_W = 54
BANNER = (
    "\n╔" + "═" * (_W + 2) + "╗\n"
    + _box_line("GridMind v{} - Agente Electrico".format(VERSION), _W) + "\n"
    + _box_line("Claude + PandaPower para analisis de red", _W) + "\n"
    + "╠" + "═" * (_W + 2) + "╣\n"
    + _box_line("Escribi tu consulta en lenguaje natural.", _W) + "\n"
    + _box_line("El agente razona y usa PandaPower para responder.", _W) + "\n"
    + "╚" + "═" * (_W + 2) + "╝\n"
    + "Comandos: /ayuda | /redes | /guardar | /reset | /salir\n"
)

AYUDA = """
  Comandos disponibles:

    /ayuda      Muestra esta ayuda
    /redes      Muestra las redes disponibles (sin costo)
    /guardar    Exporta toda la sesion a un archivo Markdown
    /historial  Muestra las consultas hechas en esta sesion
    /reset      Descarga la red actual (empezar de cero)
    /salir      Termina la sesion (tambien /exit, /quit o Ctrl+C)
"""


# ═════════════════════════════════════════════════════════════════════════
# Registro de sesión
# ═════════════════════════════════════════════════════════════════════════

class Sesion:
    """Registra consultas y respuestas para exportar con /guardar."""

    def __init__(self):
        self.inicio = datetime.now()
        self.entradas = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.costo_total = 0.0
        self.n_consultas = 0

    def registrar(self, query, result, elapsed_s):
        """Registra una consulta exitosa."""
        it = result['usage']['input_tokens']
        ot = result['usage']['output_tokens']
        costo = it / 1_000_000 * PRECIO_INPUT + ot / 1_000_000 * PRECIO_OUTPUT

        self.tokens_in += it
        self.tokens_out += ot
        self.costo_total += costo
        self.n_consultas += 1

        tools_usados = [tc['name'] for tc in result.get('tool_calls', [])]

        self.entradas.append({
            'n': self.n_consultas,
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'query': query,
            'response': result['final_text'],
            'iterations': result['iterations'],
            'tools': tools_usados,
            'input_tokens': it,
            'output_tokens': ot,
            'costo_usd': costo,
            'elapsed_s': elapsed_s,
        })

    def registrar_error(self, query, error_msg):
        """Registra una consulta fallida."""
        self.n_consultas += 1
        self.entradas.append({
            'n': self.n_consultas,
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'query': query,
            'response': f"ERROR: {error_msg}",
            'iterations': 0,
            'tools': [],
            'input_tokens': 0,
            'output_tokens': 0,
            'costo_usd': 0,
            'elapsed_s': 0,
        })

    def guardar_md(self):
        """Exporta la sesión a un archivo HTML."""
        if not self.entradas:
            return None, "No hay consultas para guardar."

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = self.inicio.strftime("%Y-%m-%d_%H%M")
        filename = LOGS_DIR / f"sesion_{ts}.html"

        duracion = datetime.now() - self.inicio
        minutos = int(duracion.total_seconds() // 60)
        segundos = int(duracion.total_seconds() % 60)

        def _bold(texto):
            return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', texto)

        def md_a_html(texto):
            lineas = texto.split('\n')
            resultado = []
            en_tabla = False
            for linea in lineas:
                stripped = linea.strip()
                if '|' in stripped and stripped.startswith('|'):
                    celdas = [c.strip() for c in stripped.split('|')[1:-1]]
                    if all(c.replace('-', '').replace(':', '') == '' for c in celdas):
                        continue
                    if not en_tabla:
                        resultado.append('<table>')
                        tag = 'th'
                        en_tabla = True
                    else:
                        tag = 'td'
                    fila = ''.join(f'<{tag}>{_bold(c)}</{tag}>' for c in celdas)
                    resultado.append(f'<tr>{fila}</tr>')
                    continue
                else:
                    if en_tabla:
                        resultado.append('</table>')
                        en_tabla = False
                if stripped.startswith('### '):
                    resultado.append(f'<h4>{_bold(stripped[4:])}</h4>')
                elif stripped.startswith('## '):
                    resultado.append(f'<h3>{_bold(stripped[3:])}</h3>')
                elif stripped.startswith('# '):
                    resultado.append(f'<h2>{_bold(stripped[2:])}</h2>')
                elif stripped == '---':
                    continue
                elif stripped.startswith('> '):
                    resultado.append(f'<div class="nota">{_bold(stripped[2:])}</div>')
                elif stripped.startswith('- '):
                    resultado.append(f'<p class="item">{_bold(stripped[2:])}</p>')
                elif stripped == '':
                    pass
                else:
                    resultado.append(f'<p>{_bold(linea)}</p>')
            if en_tabla:
                resultado.append('</table>')
            return '\n'.join(resultado)

        consultas_html = ""
        for e in self.entradas:
            tools_info = ""
            if e['tools']:
                tools_info = (f'<p class="meta">{", ".join(e["tools"])} · '
                              f'{e["iterations"]} iter · '
                              f'{e["elapsed_s"]:.1f}s · '
                              f'${e["costo_usd"]:.4f}</p>')

            consultas_html += f"""
            <section class="consulta">
                <div class="q-header">Consulta {e['n']}<span class="hora">{e['timestamp']}</span></div>
                <div class="usuario">{e['query']}</div>
                {tools_info}
                <div class="respuesta">
                    {md_a_html(e['response'])}
                </div>
            </section>
            """

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>GridMind — {self.inicio.strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            max-width: 860px;
            margin: 0 auto;
            padding: 30px 20px;
            background: #1a1a2e;
            color: #e0e0e0;
            font-size: 14px;
            line-height: 1.6;
        }}
        header {{
            border-bottom: 2px solid #7ec8e3;
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        header h1 {{
            font-size: 20px;
            font-weight: 600;
            color: #7ec8e3;
        }}
        header p {{
            color: #888;
            font-size: 12px;
            margin-top: 4px;
        }}
        .resumen {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 30px;
        }}
        .stat {{
            background: #2a2a4a;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 10px 14px;
        }}
        .stat .label {{
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat .valor {{
            font-size: 18px;
            font-weight: 600;
            color: #7ec8e3;
        }}
        .consulta {{
            background: #16213e;
            border: 1px solid #333;
            border-radius: 6px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .q-header {{
            background: #2a2a4a;
            color: #fff;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 13px;
        }}
        .q-header .hora {{
            float: right;
            font-weight: 400;
            opacity: 0.7;
        }}
        .usuario {{
            padding: 12px 16px;
            background: #1a1a3a;
            border-bottom: 1px solid #333;
            font-style: italic;
            color: #bbb;
        }}
        .meta {{
            padding: 6px 16px;
            font-size: 11px;
            color: #999;
            background: #1a1a30;
            border-bottom: 1px solid #222;
        }}
        .respuesta {{
            padding: 16px;
        }}
        .respuesta h2 {{
            font-size: 16px;
            color: #7ec8e3;
            margin: 16px 0 8px;
            padding-bottom: 4px;
            border-bottom: 1px solid #333;
        }}
        .respuesta h3 {{
            font-size: 15px;
            color: #5b9bd5;
            margin: 14px 0 6px;
        }}
        .respuesta h4 {{
            font-size: 14px;
            color: #5b9bd5;
            margin: 12px 0 6px;
        }}
        .respuesta p {{
            margin: 6px 0;
        }}
        .respuesta .item {{
            padding-left: 16px;
            position: relative;
        }}
        .respuesta .item::before {{
            content: "—";
            position: absolute;
            left: 0;
            color: #666;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 10px 0;
            font-size: 13px;
        }}
        th {{
            background: #2a2a4a;
            color: #7ec8e3;
            padding: 8px 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 7px 12px;
            border-bottom: 1px solid #333;
        }}
        tr:hover td {{
            background: #1e1e3a;
        }}
        .nota {{
            background: #2e1a2e;
            border-left: 3px solid #ff55ff;
            padding: 8px 12px;
            margin: 10px 0;
            font-size: 13px;
            color: #ff99ff;
        }}
        strong {{
            font-weight: 600;
            color: #ffffff;
        }}
    </style>
</head>
<body>
    <header>
        <h1>GridMind</h1>
        <p>Sesion del {self.inicio.strftime('%d/%m/%Y')} a las {self.inicio.strftime('%H:%M')} · Duracion: {minutos}min {segundos}s</p>
    </header>

    <div class="resumen">
        <div class="stat"><div class="label">Consultas</div><div class="valor">{self.n_consultas}</div></div>
        <div class="stat"><div class="label">Tokens</div><div class="valor">{self.tokens_in + self.tokens_out:,}</div></div>
        <div class="stat"><div class="label">Tiempo</div><div class="valor">{minutos}:{segundos:02d}</div></div>
        <div class="stat"><div class="label">Costo</div><div class="valor">${self.costo_total:.4f}</div></div>
    </div>

    {consultas_html}
</body>
</html>"""

        filename.write_text(html, encoding='utf-8')
        return filename, None

    def mostrar_historial(self):
        """Muestra resumen de consultas en la sesión."""
        if not self.entradas:
            print("  No hay consultas en esta sesión.")
            return
        print("\n  Historial de sesión:")
        for e in self.entradas:
            estado = "OK" if 'ERROR' not in e['response'] else "ERROR"
            print(f"    [{e['timestamp']}] ({estado}) {e['query'][:65]}")
        print(f"\n  Total: {self.n_consultas} consultas | "
              f"Costo acumulado: ${self.costo_total:.4f} USD")
        
        

# ═════════════════════════════════════════════════════════════════════════
# Loop principal
# ═════════════════════════════════════════════════════════════════════════


def _formatear_respuesta(texto):
    """Convierte Markdown básico a colores ANSI para terminal."""
    BOLD = '\033[1m'
    RESET = '\033[0m'
    AZUL = '\033[94m'
    MAGENTA = '\033[95m'

    lineas = texto.split('\n')
    resultado = []

    for linea in lineas:
        if linea.startswith('#'):
            limpia = linea.lstrip('#').strip()
            resultado.append(f"{BOLD}{AZUL}{limpia}{RESET}")
        elif linea.startswith('>'):
            limpia = linea.lstrip('>').strip()
            resultado.append(f"{MAGENTA}{limpia}{RESET}")
        else:
            linea = re.sub(r'\*\*(.+?)\*\*', rf'{BOLD}\1{RESET}', linea)
            resultado.append(linea)

    return '\n'.join(resultado)


def main():
    print(BANNER)
    sesion = Sesion()

    while True:
        try:
            user_input = input("\nTú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nHasta luego.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # --- Comandos especiales ---

        if cmd in ("/salir", "/exit", "/quit"):
            if sesion.entradas:
                print(f"\n  Sesión: {sesion.n_consultas} consultas, "
                      f"costo total ${sesion.costo_total:.4f} USD")
                print("  Usá /guardar antes de salir si querés exportar.")
                confirmar = input("  Salir sin guardar? (s/n): ").strip().lower()
                if confirmar not in ('s', 'si', 'sí', 'y', 'yes', ''):
                    continue
            print("\nHasta luego.")
            break

        if cmd == "/reset":
            reset_network()
            print("  Red descargada. La próxima consulta cargará la red desde cero.")
            continue

        if cmd in ("/ayuda", "/help"):
            print(AYUDA)
            continue

        if cmd == "/historial":
            sesion.mostrar_historial()
            continue

        if cmd == "/guardar":
            filepath, error = sesion.guardar_md()
            if error:
                print(f"  {error}")
            else:
                print(f"\n  Sesión exportada a: {filepath}")
                print(f"  {sesion.n_consultas} consultas | "
                      f"costo total ${sesion.costo_total:.4f} USD")
            continue
        
        if cmd == "/redes":
            print("\n  Redes disponibles:\n")
            for nombre, info in AVAILABLE_NETWORKS.items():
                print(f"    {nombre:20s} {info['descripcion']}")
            print(f"\n  Total: {len(AVAILABLE_NETWORKS)} redes.")
            print("  Ejemplo: 'Carga la red IEEE_30 y dame un resumen'")
            continue

        # --- Consulta al agente ---
        print("\nGridMind está pensando...\n")

        t0 = time.time()
        try:
            result = run_react_loop(user_query=user_input, verbose=True)
            elapsed = time.time() - t0

            n_tools = len(result.get('tool_calls', []))
            it = result['usage']['input_tokens']
            ot = result['usage']['output_tokens']
            costo = it / 1_000_000 * PRECIO_INPUT + ot / 1_000_000 * PRECIO_OUTPUT

            print(f"\nGridMind: {_formatear_respuesta(result['final_text'])}")
            print(f"\n   [{result['iterations']} iter | {n_tools} tools | "
                  f"{it+ot:,} tokens | ${costo:.4f} | {elapsed:.1f}s | "
                  f"sesión: ${sesion.costo_total + costo:.4f}]")

            sesion.registrar(user_input, result, elapsed)

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  Error al procesar: {e}")
            print("  Probá con /reset si el problema persiste.")
            sesion.registrar_error(user_input, str(e))
            
        


if __name__ == "__main__":
    main()
