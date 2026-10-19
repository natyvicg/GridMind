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
    /guardar    Exporta la sesión completa a un archivo HTML
    /historial  Muestra las consultas hechas en esta sesión
    /reset      Limpia la red cargada y el historial (empezás de cero)
    /olvidar    Borra el historial de conversación, conserva la red
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
from tools import reset_network, _STATE


# ═════════════════════════════════════════════════════════════════════════
# Configuración
# ═════════════════════════════════════════════════════════════════════════

VERSION = "1.4.0"

# Precios Claude Sonnet (USD por millón de tokens)
PRECIO_INPUT  = 3.00
PRECIO_OUTPUT = 15.00

LOGS_DIR = Path("logs")

# --- Memoria de la conversación ---
# Se recuerdan los últimos turnos como pares consulta/respuesta. NO se
# guardan los resultados crudos de las herramientas: en la red CR un
# solo resultado puede traer cientos de filas, y reenviarlo en cada
# iteración del loop dispararía el costo sin aportar al razonamiento.
MAX_TURNOS_HISTORIAL = 4          # consultas anteriores que se recuerdan
MAX_CHARS_RESPUESTA_HISTORIAL = 1200

_W = 58
_SEP = "  " + "─" * _W

def _center(text, width=_W + 2):
    """Centra texto en el ancho dado."""
    return text.center(width)


BANNER = (
    "\n  ╔" + "═" * _W + "╗\n"
    + "  ║" + _center("GridMind v{}".format(VERSION), _W) + "║\n"
    + "  ║" + _center("Agente de IA para análisis de redes eléctricas", _W) + "║\n"
    + "  ╚" + "═" * _W + "╝\n"
    + "\n"
    + "  GridMind recibe consultas en lenguaje natural, razona\n"
    + "  sobre el problema y ejecuta simulaciones en PandaPower\n"
    + "  para entregar resultados numéricos reales.\n"
    + "\n"
    + _SEP + "\n"
    + "  Ejemplos de consultas:\n"
    + "\n"
    + "    > Carga la red IEEE_14 y dame un resumen del estado\n"
    + "    > ¿Cuáles barras tienen violaciones de tensión en CR_Max?\n"
    + "    > Desconecta la línea 1-5 de IEEE_14 y analiza el impacto\n"
    + "    > Corré un cortocircuito trifásico en CR_Med y dame las 5 barras\n"
    + "      con mayor corriente de falla\n"
    + "\n"
    + _SEP + "\n"
    + "  Comandos:\n"
    + "\n"
    + "    /redes       Ver las 18 redes disponibles\n"
    + "    /guardar     Exportar la sesión a HTML\n"
    + "    /historial   Consultas realizadas en esta sesión\n"
    + "    /reset       Descargar la red actual y olvidar el historial\n"
    + "    /olvidar     Olvidar la conversación, conservando la red\n"
    + "    /ayuda       Más información sobre GridMind\n"
    + "    /salir       Terminar sesión\n"
)

AYUDA = """
  Comandos disponibles:
  ──────────────────────────────────────────────────────────

    /redes      Muestra las 18 redes disponibles (IEEE + Costa Rica)
    /guardar    Exporta la sesión completa a un archivo HTML
    /historial  Muestra las consultas hechas en esta sesión
    /reset      Descarga la red actual y borra el historial
    /olvidar    Borra el historial de conversación, conserva la red
    /salir      Termina la sesión. Pregunta si guardar el HTML;
                dar Enter guarda y sale (también /exit o /quit)
    /ayuda      Muestra esta ayuda

  Memoria:
  ──────────────────────────────────────────────────────────

    GridMind recuerda las últimas 4 consultas de la sesión, así
    que podés escribir "hacé lo mismo en IEEE_14" o "compará con
    lo anterior" y entiende a qué te referís. Si una consulta
    queda ambigua, pregunta en vez de adivinar.

    Solo se recuerdan las preguntas y las respuestas, no los
    resultados crudos de las herramientas.

  Sobre GridMind:
  ──────────────────────────────────────────────────────────

    Usa el patrón ReAct (razonamiento + acción): el agente
    decide qué herramienta de PandaPower necesita, Python la
    ejecuta, y el resultado vuelve al agente para seguir
    razonando o responder.

    Redes: 15 IEEE estándar (4 a 300 barras) + 3 escenarios
    de la red eléctrica de Costa Rica (524 barras, marzo 2023).

  Análisis disponibles:
  ──────────────────────────────────────────────────────────

    Flujo de potencia (Newton-Raphson), violaciones de
    tensión, cargabilidad de líneas, contingencias N-1,
    modificación de cargas y cortocircuito trifásico
    según IEC 60909.

    El cortocircuito requiere impedancia de fuente, que solo
    traen las redes de Costa Rica. En las redes IEEE el agente
    lo informa en vez de estimar valores.
"""


# ═════════════════════════════════════════════════════════════════════════
# Registro de sesión
# ═════════════════════════════════════════════════════════════════════════

def _iteraciones_nr(tool_calls):
    """
    Extrae el número de iteraciones de Newton-Raphson de las llamadas a
    run_power_flow de una consulta. Devuelve la última reportada, o None
    si la consulta no corrió flujo de potencia.

    Es distinto de las iteraciones del agente: esto mide el esfuerzo
    numérico del solver, aquello mide los ciclos de razonamiento.
    """
    valor = None
    for tc in tool_calls or []:
        if tc.get('name') != 'run_power_flow':
            continue
        res = tc.get('result')
        if isinstance(res, dict) and res.get('iterations_nr') is not None:
            valor = res['iterations_nr']
    return valor


class Sesion:
    """Registra consultas y respuestas para exportar con /guardar."""

    def __init__(self):
        self.inicio = datetime.now()
        self.entradas = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.costo_total = 0.0
        self.n_consultas = 0
        self.iteraciones_agente = 0
        self.tiempo_total_s = 0.0
        # Índice a partir del cual se construye el historial. /olvidar y
        # /reset lo mueven al final, sin borrar el registro de la sesión:
        # el HTML exportado sigue conteniendo todas las consultas.
        self.corte_historial = 0

    def registrar(self, query, result, elapsed_s):
        """Registra una consulta exitosa."""
        it = result['usage']['input_tokens']
        ot = result['usage']['output_tokens']
        costo = it / 1_000_000 * PRECIO_INPUT + ot / 1_000_000 * PRECIO_OUTPUT

        self.tokens_in += it
        self.tokens_out += ot
        self.costo_total += costo
        self.n_consultas += 1

        tool_calls = result.get('tool_calls', [])
        tools_usados = [tc['name'] for tc in tool_calls]

        self.iteraciones_agente += result['iterations']
        self.tiempo_total_s += elapsed_s

        self.entradas.append({
            'n': self.n_consultas,
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'query': query,
            'response': result['final_text'],
            'iterations': result['iterations'],
            'iterations_nr': _iteraciones_nr(tool_calls),
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
            'iterations_nr': None,
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
            # Código entre acentos graves primero: si se procesa después,
            # los asteriscos dentro de un identificador se interpretarían
            # como formato.
            texto = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', texto)
            # Negrita antes que cursiva, para que el patrón de cursiva no
            # se coma los asteriscos dobles.
            texto = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', texto)
            return re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<em>\1</em>', texto)

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
                        resultado.append('<div class="tabla"><table>')
                        tag = 'th'
                        en_tabla = True
                    else:
                        tag = 'td'
                    fila = ''.join(f'<{tag}>{_bold(c)}</{tag}>' for c in celdas)
                    resultado.append(f'<tr>{fila}</tr>')
                    continue
                else:
                    if en_tabla:
                        resultado.append('</table></div>')
                        en_tabla = False
                # De más profundo a menos: si se evalúa '# ' primero, un
                # '#### ' nunca coincide con ninguno y sale como texto plano
                # con los numerales visibles.
                if stripped.startswith('##### '):
                    resultado.append(f'<h5>{_bold(stripped[6:])}</h5>')
                elif stripped.startswith('#### '):
                    resultado.append(f'<h5>{_bold(stripped[5:])}</h5>')
                elif stripped.startswith('### '):
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
                resultado.append('</table></div>')
            return '\n'.join(resultado)

        nr = [e['iterations_nr'] for e in self.entradas
              if e.get('iterations_nr') is not None]
        if nr:
            iter_nr_txt = str(min(nr)) if min(nr) == max(nr) else \
                "{}-{}".format(min(nr), max(nr))
        else:
            iter_nr_txt = "—"

        promedio_txt = (
            "{:.1f} s".format(self.tiempo_total_s / self.n_consultas)
            if self.n_consultas else "—"
        )

        consultas_html = ""
        for e in self.entradas:
            # La metadata se arma siempre, incluso cuando el agente
            # respondió sin llamar herramientas (por ejemplo, resolviendo
            # una comparación con lo que ya estaba en el historial).
            if e['tools']:
                partes = [f'<strong>Herramientas:</strong> {", ".join(e["tools"])}']
            else:
                partes = ['<strong>Sin herramientas</strong> '
                          '(respondida desde el contexto de la sesión)']

            n_it = e["iterations"]
            partes.append(
                f'{n_it} {"iteración" if n_it == 1 else "iteraciones"} del agente'
            )
            if e.get('iterations_nr') is not None:
                n_nr = e["iterations_nr"]
                partes.append(
                    f'{n_nr} {"iteración" if n_nr == 1 else "iteraciones"} '
                    f'Newton-Raphson'
                )
            partes.append(f'{e["elapsed_s"]:.1f} s')
            partes.append(f'{e["input_tokens"] + e["output_tokens"]:,} tokens')
            partes.append(f'${e["costo_usd"]:.4f}')
            tools_info = f'<p class="meta">{" · ".join(partes)}</p>' 

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
        /* ---------------------------------------------------------------
           Paleta "gris técnico": gris muy claro, verde petróleo como
           acento y barra gris grafito. El acento es apagado a propósito,
           para que lo primero que se lea en una tabla sean las cifras y
           no el color. Los tokens están arriba: cambiar la paleta es
           cambiar estos valores.
           --------------------------------------------------------------- */
        :root {{
            --fondo:         #f5f6f7;
            --texto:         #232729;
            --panel:         #ffffff;
            --tarjeta:       #ffffff;
            --borde:         #d5d9dc;
            --borde-tabla:   #e4e7ea;
            --borde-acento:  #b9c0c4;
            --acento:        #2c6e6a;
            --acento-fuerte: #1e4f4c;
            --enfasis:       #14181a;
            --suave:         #5d666b;
            --barra:         #2f3437;
            --barra-texto:   #f2f4f5;
            --usuario:       #fafbfb;
            --metafondo:     #fbfcfc;
            --th:            #eceff0;
            --th-texto:      #1e4f4c;
            --fila-hover:    #f4f7f7;
            --nota-fondo:    #eef4f3;
            --nota-borde:    #2c6e6a;
            --nota-texto:    #274f4c;
            --codigo-fondo:  #edf0f1;
            --codigo-texto:  #1e4f4c;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system,
                         'Helvetica Neue', Arial, sans-serif;
            max-width: 920px;
            margin: 0 auto;
            padding: 34px 22px;
            background: var(--fondo);
            color: var(--texto);
            font-size: 16.5px;
            line-height: 1.75;
        }}

        header {{
            border-bottom: 2px solid var(--acento);
            padding-bottom: 13px;
            margin-bottom: 20px;
        }}
        header h1 {{
            font-size: 26px;
            font-weight: 600;
            color: var(--acento-fuerte);
            letter-spacing: 0.3px;
        }}
        header p {{
            color: var(--suave);
            font-size: 14px;
            margin-top: 5px;
        }}

        .resumen {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
            gap: 10px;
            margin-bottom: 18px;
        }}
        .stat {{
            background: var(--tarjeta);
            border: 1px solid var(--borde);
            border-radius: 5px;
            padding: 12px 16px;
        }}
        .stat .label {{
            font-size: 12.5px;
            color: var(--suave);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat .valor {{
            font-size: 23px;
            font-weight: 600;
            color: var(--acento-fuerte);
            font-variant-numeric: tabular-nums;
        }}

        .glosario {{
            font-size: 13.5px;
            color: var(--suave);
            border-left: 3px solid var(--borde-acento);
            padding: 7px 13px;
            margin-bottom: 26px;
            line-height: 1.6;
        }}
        .glosario strong {{
            color: var(--acento-fuerte);
            font-weight: 600;
        }}

        .consulta {{
            background: var(--panel);
            border: 1px solid var(--borde);
            border-radius: 6px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .q-header {{
            background: var(--barra);
            color: var(--barra-texto);
            padding: 10px 18px;
            font-weight: 600;
            font-size: 15px;
        }}
        .q-header .hora {{
            float: right;
            font-weight: 400;
            opacity: 0.75;
        }}
        .usuario {{
            padding: 14px 18px;
            font-size: 16.5px;
            background: var(--usuario);
            border-bottom: 1px solid var(--borde);
            font-style: italic;
            color: var(--suave);
        }}
        .meta {{
            padding: 8px 18px;
            font-size: 13px;
            color: var(--suave);
            background: var(--metafondo);
            border-bottom: 1px solid var(--borde);
            font-variant-numeric: tabular-nums;
        }}
        .meta strong {{ color: var(--acento-fuerte); }}

        .respuesta {{ padding: 18px; }}
        .respuesta h2 {{
            font-size: 21px;
            color: var(--acento-fuerte);
            margin: 16px 0 8px;
            padding-bottom: 4px;
            border-bottom: 1px solid var(--borde);
        }}
        .respuesta h3 {{
            font-size: 19px;
            color: var(--acento-fuerte);
            margin: 14px 0 6px;
        }}
        .respuesta h4 {{
            font-size: 17px;
            color: var(--acento);
            margin: 14px 0 6px;
        }}
        .respuesta h5 {{
            font-size: 15.5px;
            color: var(--acento);
            margin: 12px 0 4px;
            font-weight: 600;
        }}
        .respuesta p {{ margin: 8px 0; }}
        .respuesta .item {{
            padding-left: 17px;
            position: relative;
        }}
        .respuesta .item::before {{
            content: "—";
            position: absolute;
            left: 0;
            color: var(--borde-acento);
        }}
        .respuesta em {{ color: var(--suave); }}

        code {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 0.92em;
            background: var(--codigo-fondo);
            color: var(--codigo-texto);
            padding: 1px 5px;
            border-radius: 3px;
        }}

        /* Contenedor con desplazamiento propio: con la tipografía más
           grande, una tabla de seis columnas puede no caber, y es preferible
           que se desplace ella sola antes que toda la página. */
        .tabla {{
            overflow-x: auto;
            margin: 12px 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            font-size: 15px;
            /* Cifras de ancho fijo: las columnas numéricas quedan alineadas. */
            font-variant-numeric: tabular-nums;
        }}
        th {{
            background: var(--th);
            color: var(--th-texto);
            padding: 10px 14px;
            text-align: left;
            font-weight: 600;
            white-space: nowrap;
            border-bottom: 1px solid var(--borde);
        }}
        td {{
            padding: 9px 14px;
            border-bottom: 1px solid var(--borde-tabla);
        }}
        tr:hover td {{ background: var(--fila-hover); }}

        .nota {{
            background: var(--nota-fondo);
            border-left: 4px solid var(--nota-borde);
            padding: 11px 15px;
            margin: 13px 0;
            font-size: 15px;
            color: var(--nota-texto);
            line-height: 1.65;
        }}

        strong {{
            font-weight: 600;
            color: var(--enfasis);
        }}

        /* ---------------------------------------------------------------
           Impresión: el reporte de sesión es evidencia del TFG y puede
           terminar impreso o adjunto a un documento.
           --------------------------------------------------------------- */
        @media print {{
            body {{
                background: #ffffff;
                max-width: 100%;
                padding: 0;
                font-size: 10.5pt;
                line-height: 1.5;
            }}
            .consulta {{
                break-inside: avoid;
                page-break-inside: avoid;
                margin-bottom: 14px;
            }}
            .tabla {{ overflow-x: visible; }}
            table {{ font-size: 9.5pt; }}
            th, td {{ padding: 5px 8px; }}
            .q-header, .stat, .nota, th {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .glosario {{ font-size: 9pt; }}
            .meta {{ font-size: 8.5pt; }}
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
        <div class="stat"><div class="label">Iteraciones agente</div><div class="valor">{self.iteraciones_agente}</div></div>
        <div class="stat"><div class="label">Iteraciones NR</div><div class="valor">{iter_nr_txt}</div></div>
        <div class="stat"><div class="label">Tokens</div><div class="valor">{self.tokens_in + self.tokens_out:,}</div></div>
        <div class="stat"><div class="label">Cómputo</div><div class="valor">{self.tiempo_total_s:.1f} s</div></div>
        <div class="stat"><div class="label">Costo</div><div class="valor">${self.costo_total:.4f}</div></div>
    </div>

    <p class="glosario"><strong>Iteraciones del agente:</strong> ciclos de razonamiento del modelo
    (consulta a la API, ejecución de herramienta, retorno del resultado). <strong>Iteraciones NR:</strong>
    iteraciones que le tomó converger al método de Newton-Raphson en PandaPower. Son procesos
    distintos: el primero mide el razonamiento, el segundo el esfuerzo numérico del solver.
    <strong>Cómputo:</strong> tiempo efectivo que el sistema tardó en producir las respuestas,
    {promedio_txt} por consulta en promedio; la duración del encabezado incluye además el tiempo
    entre consultas.</p>

    {consultas_html}
</body>
</html>"""

        filename.write_text(html, encoding='utf-8')
        return filename, None

    def historial_para_agente(self, max_turnos=MAX_TURNOS_HISTORIAL,
                              max_chars=MAX_CHARS_RESPUESTA_HISTORIAL):
        """
        Devuelve los últimos turnos como lista de mensajes para la API.

        Solo pares consulta/respuesta, sin resultados de herramientas.
        Se omiten las consultas que terminaron en error y las anteriores
        al corte fijado por /olvidar o /reset.
        """
        utiles = [
            e for e in self.entradas[self.corte_historial:]
            if not str(e["response"]).startswith("ERROR:")
        ]

        mensajes = []
        for e in utiles[-max_turnos:]:
            respuesta = e["response"] or ""
            if len(respuesta) > max_chars:
                respuesta = respuesta[:max_chars] + "\n[...respuesta recortada]"
            mensajes.append({"role": "user", "content": e["query"]})
            mensajes.append({"role": "assistant", "content": respuesta})
        return mensajes

    def olvidar(self):
        """Corta el historial que ve el agente. No borra el registro."""
        recordadas = len(self.entradas) - self.corte_historial
        self.corte_historial = len(self.entradas)
        return recordadas

    def mostrar_historial(self):
        """Muestra resumen de consultas en la sesión."""
        if not self.entradas:
            print("  No hay consultas en esta sesión.")
            return
        print("\n  Historial de sesión:")
        for i, e in enumerate(self.entradas):
            estado = "OK" if 'ERROR' not in e['response'] else "ERROR"
            marca = "  " if i >= self.corte_historial else "· "
            print(f"    {marca}[{e['timestamp']}] ({estado}) {e['query'][:63]}")
        n_ctx = len(self.historial_para_agente()) // 2
        print(f"\n  El agente recuerda las últimas {n_ctx} consulta(s). "
              f"Las marcadas con · quedaron fuera del contexto.")
        print(f"\n  Total: {self.n_consultas} consultas | "
              f"{self.iteraciones_agente} iteraciones del agente | "
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
            if not sesion.entradas:
                print("\nHasta luego.")
                break

            print(f"\n  Sesión: {sesion.n_consultas} consultas, "
                  f"{sesion.iteraciones_agente} iteraciones, "
                  f"costo total ${sesion.costo_total:.4f} USD")
            print("\n    s  guardar la sesión en HTML y salir  (por defecto)")
            print("    n  salir SIN guardar")
            print("    c  cancelar y seguir trabajando")

            try:
                opcion = input("\n  Opción [s/n/c]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n  Cancelado. Seguimos.")
                continue

            # El default (Enter) es la opción segura: guardar.
            if opcion in ("", "s", "si", "sí", "y", "yes", "guardar"):
                filepath, error = sesion.guardar_md()
                if error:
                    print(f"\n  {error}")
                    print("  No se guardó nada. Seguimos en la sesión.")
                    continue
                print(f"\n  Sesión exportada a: {filepath}")
                print("\nHasta luego.")
                break

            if opcion in ("n", "no"):
                print("\n  Saliendo sin guardar.")
                print("\nHasta luego.")
                break

            if opcion in ("c", "cancelar", "cancel"):
                print("\n  Cancelado. Seguimos trabajando.")
                continue

            print(f"\n  No entendí '{opcion}'. No se hizo nada, seguimos "
                  f"en la sesión.")
            print("  Escribí /salir de nuevo cuando quieras terminar.")
            continue

        if cmd == "/reset":
            reset_network()
            olvidadas = sesion.olvidar()
            print("  Red descargada. La próxima consulta cargará la red desde cero.")
            if olvidadas:
                print(f"  También se olvidaron {olvidadas} consulta(s) del contexto.")
            continue

        if cmd in ("/olvidar", "/forget"):
            olvidadas = sesion.olvidar()
            if olvidadas:
                print(f"  Historial borrado: el agente ya no recuerda las "
                      f"{olvidadas} consulta(s) anteriores.")
            else:
                print("  No había historial que olvidar.")
            print("  La red cargada se conserva.")
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

        # Inyectar contexto de estado para que el LLM sepa qué red hay
        # cargada sin necesidad de historial de conversación completo.
        contexto = ""
        if _STATE["current_network_name"]:
            contexto = (
                "[Red actualmente cargada: {}. Si la consulta se refiere a "
                "\"esta red\" o no especifica cuál, use esta.]\n\n".format(
                    _STATE["current_network_name"]
                )
            )

        t0 = time.time()
        try:
            result = run_react_loop(
                user_query=contexto + user_input,
                verbose=True,
                historial=sesion.historial_para_agente(),
            )
            elapsed = time.time() - t0

            n_tools = len(result.get('tool_calls', []))
            it = result['usage']['input_tokens']
            ot = result['usage']['output_tokens']
            costo = it / 1_000_000 * PRECIO_INPUT + ot / 1_000_000 * PRECIO_OUTPUT

            it_nr = _iteraciones_nr(result.get('tool_calls'))
            nr_txt = f" | NR: {it_nr} iter" if it_nr is not None else ""

            print(f"\nGridMind: {_formatear_respuesta(result['final_text'])}")
            n_recordadas = len(sesion.historial_para_agente()) // 2
            ctx_txt = f" | contexto: {n_recordadas}" if n_recordadas else ""

            print(f"\n   [agente: {result['iterations']} iter{nr_txt}{ctx_txt} | "
                  f"{n_tools} tools | {it+ot:,} tokens | ${costo:.4f} | "
                  f"{elapsed:.1f}s | sesión: ${sesion.costo_total + costo:.4f}]")

            sesion.registrar(user_input, result, elapsed)

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  Error al procesar: {e}")
            print("  Probá con /reset si el problema persiste.")
            sesion.registrar_error(user_input, str(e))
            
        


if __name__ == "__main__":
    main()
