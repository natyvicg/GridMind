"""
correr_bateria.py — Batería de pruebas del agente sobre la red CR.

Garantías que ofrece esta versión:

  1. RESUME automático: si existe logs/log_bateria_v1.json con consultas
     exitosas de una corrida previa, las salta. Solo corre las que faltan.
     Protege contra pagar dos veces por la misma consulta.

  2. TIMEOUT en cliente Anthropic: 90 s por request, con 2 reintentos. Si
     un call HTTP se cuelga (caso de la corrida anterior), aborta solo
     y la batería sigue.

  3. PERSISTENCIA INCREMENTAL: tras CADA consulta exitosa, se reescribe
     logs/log_bateria_v1.json. Si el script crashea o se interrumpe, lo
     ya pagado queda guardado.

  4. Precarga de las 3 redes CR antes del agente, con prints visibles, así
     el costo (gratis) de construcción no se mezcla con el costo (pago)
     del agente.

  5. verbose=True en el ReAct loop: cada tool_use se imprime en pantalla
     en tiempo real.

Uso:
    python correr_bateria.py
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from agent import run_react_loop
from red_cr_loader import cargar_red_cr


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

PRECIO_INPUT_USD_POR_MTOK = 3.00
PRECIO_OUTPUT_USD_POR_MTOK = 15.00

TIMEOUT_API_S = 90.0       # Timeout por llamada HTTP a Anthropic.
MAX_RETRIES_API = 2        # Reintentos automáticos del SDK.

LOG_JSON = Path("logs/log_bateria_v1.json")
LOG_MD = Path("logs/log_bateria_v1.md")


def costo_usd(usage):
    return (
        usage["input_tokens"] / 1_000_000 * PRECIO_INPUT_USD_POR_MTOK
        + usage["output_tokens"] / 1_000_000 * PRECIO_OUTPUT_USD_POR_MTOK
    )


def hms():
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Batería de consultas
# ---------------------------------------------------------------------------

ESCENARIOS = ["CR_Min", "CR_Med", "CR_Max"]

CONSULTAS = [
    {
        "id": "Q1_resumen",
        "plantilla": (
            "Carga la red {esc} y reporta Vmin, Vmax (en pu) y la carga "
            "máxima de línea (en %). Indícame también cuántas barras tiene "
            "la red y cuántas tienen resultado válido."
        ),
    },
    {
        "id": "Q2_subtensiones",
        "plantilla": (
            "En la red {esc}, ¿cuántas barras presentan subtensión "
            "(< 0.95 pu)? Lista las 5 barras con menor tensión, indicando "
            "su índice de barra y el valor de tensión en pu."
        ),
    },
    {
        "id": "Q3_sobrecargas",
        "plantilla": (
            "En la red {esc}, ¿hay líneas sobrecargadas (carga > 100%)? "
            "Si las hay, dime cuántas son en total y lista hasta 5 con "
            "el índice de línea, las barras de extremo y el porcentaje "
            "de carga."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

def cargar_resultados_previos():
    """Lee logs/log_bateria_v1.json si existe. Devuelve lista vacía si no."""
    if not LOG_JSON.exists():
        return []
    try:
        data = json.loads(LOG_JSON.read_text(encoding="utf-8"))
        return data.get("resultados", [])
    except Exception as e:
        print(f"[{hms()}] AVISO: no se pudo leer log previo ({e}). "
              f"Iniciando desde cero.")
        return []


def guardar_estado(resultados, totales):
    """Escribe el estado actual al disco. Llamado tras cada consulta exitosa."""
    LOG_JSON.parent.mkdir(exist_ok=True)
    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {"resultados": resultados, "totales": totales},
            f, ensure_ascii=False, indent=2, default=str,
        )


def consulta_ya_hecha(resultados, esc, cons_id):
    """¿Existe en `resultados` una entrada exitosa para (esc, cons_id)?"""
    for r in resultados:
        if (r.get("escenario") == esc
                and r.get("consulta_id") == cons_id
                and r.get("error") is None):
            return True
    return False


def reset_estado():
    import tools
    tools._STATE["net"] = None
    tools._STATE["current_network_name"] = None


def precargar_redes_cr():
    print(f"[{hms()}] Precargando redes CR (sin agente, sin costo USD)...")
    for esc in ("Min", "Med", "Max"):
        t0 = time.time()
        print(f"  [{hms()}] Construyendo CR_{esc}...", end="", flush=True)
        net = cargar_red_cr(esc)
        elapsed = time.time() - t0
        vmin = net.res_bus.vm_pu.dropna().min()
        vmax = net.res_bus.vm_pu.dropna().max()
        print(f" listo en {elapsed:.1f}s | Vmin={vmin:.4f} Vmax={vmax:.4f}")
    print(f"[{hms()}] Precarga completa.\n")


def escribir_markdown(resultados, totales):
    """Genera log_bateria_v1.md a partir del estado actual."""
    md_lines = []
    md_lines.append("# Logs de consultas GridMind sobre red CR\n")
    md_lines.append(f"Modelo: claude-sonnet-4-6  ·  Escenarios: {ESCENARIOS}\n")
    md_lines.append("\n## Totales\n")
    n_ok = sum(1 for r in resultados if r.get("error") is None)
    md_lines.append(f"- Consultas exitosas: {n_ok} / {len(resultados)}")
    md_lines.append(f"- Tokens input totales: {totales['input_tokens']:,}")
    md_lines.append(f"- Tokens output totales: {totales['output_tokens']:,}")
    md_lines.append(f"- Costo total estimado: ${totales['costo_usd']:.4f} USD\n")

    for r in resultados:
        md_lines.append(f"\n---\n\n## {r['escenario']} · {r['consulta_id']}\n")
        md_lines.append(f"**Consulta:** {r['query']}\n")
        if r.get("error"):
            md_lines.append(f"\n**ERROR:** `{r['error']}`\n")
            continue
        md_lines.append(f"\n**Iteraciones:** {r['iterations']}  "
                        f"·  **Stop reason:** `{r['stop_reason']}`  "
                        f"·  **Tiempo:** {r['elapsed_s']:.1f} s\n")
        md_lines.append(
            f"\n**Usage:** in={r['usage']['input_tokens']}, "
            f"out={r['usage']['output_tokens']}, "
            f"costo=${r['costo_usd']:.4f}\n"
        )
        md_lines.append("\n**Tool calls:**\n")
        if not r["tool_calls"]:
            md_lines.append("- (ninguna)\n")
        else:
            for tc in r["tool_calls"]:
                md_lines.append(f"- `{tc['name']}({tc['input']})`")
                res = tc["result"]
                if isinstance(res, dict):
                    if "error" in res:
                        md_lines.append(f"  - ERROR: {res['error']}")
                    else:
                        keys_breves = [k for k in res.keys()
                                       if k not in ("violations", "overloaded_lines")]
                        resumen = {k: res[k] for k in keys_breves}
                        md_lines.append(f"  - resumen: `{resumen}`")
                        if "violations" in res:
                            md_lines.append(f"  - violations[:3]: `{res['violations'][:3]}`")
                        if "overloaded_lines" in res:
                            md_lines.append(f"  - overloaded[:3]: `{res['overloaded_lines'][:3]}`")
        md_lines.append("\n**Respuesta final:**\n")
        md_lines.append("```\n" + r["final_text"] + "\n```\n")

    LOG_MD.parent.mkdir(exist_ok=True)
    with open(LOG_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


# ---------------------------------------------------------------------------
# Recalcular totales desde la lista de resultados
# ---------------------------------------------------------------------------

def recalcular_totales(resultados):
    t = {"input_tokens": 0, "output_tokens": 0, "costo_usd": 0.0}
    for r in resultados:
        if r.get("error") is None and "usage" in r:
            t["input_tokens"] += r["usage"]["input_tokens"]
            t["output_tokens"] += r["usage"]["output_tokens"]
            t["costo_usd"] += r.get("costo_usd", 0.0)
    return t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY en .env")

    # Cliente Anthropic con timeout y reintentos automáticos.
    client = Anthropic(
        api_key=api_key,
        timeout=TIMEOUT_API_S,
        max_retries=MAX_RETRIES_API,
    )

    print("=" * 70)
    print("DÍA 6 — Batería de consultas GridMind sobre red Costa Rica")
    print("=" * 70)

    # Cargar resultados previos para modo resume.
    resultados = cargar_resultados_previos()
    totales = recalcular_totales(resultados)

    if resultados:
        n_ok = sum(1 for r in resultados if r.get("error") is None)
        print(f"\n[{hms()}] RESUME: encontradas {n_ok} consultas exitosas previas "
              f"(${totales['costo_usd']:.4f} USD ya pagados).")
        print(f"         Solo se ejecutarán las consultas que faltan.\n")

    precargar_redes_cr()

    for esc in ESCENARIOS:
        print(f"\n--- Escenario: {esc} ---")
        reset_estado()

        for cons in CONSULTAS:
            # Skip si ya está hecha.
            if consulta_ya_hecha(resultados, esc, cons["id"]):
                print(f"[{hms()}] [{cons['id']}] SKIP (ya en log).")
                continue

            query = cons["plantilla"].format(esc=esc)
            print(f"\n[{hms()}] [{cons['id']}] {query[:80]}...")

            t0 = time.time()
            error = None
            out = None

            try:
                out = run_react_loop(query, client=client, verbose=True)
            except KeyboardInterrupt:
                print(f"  [{hms()}] Interrupción manual. "
                      f"Estado guardado en {LOG_JSON}.")
                # Antes de salir, guardar estado actual.
                guardar_estado(resultados, totales)
                escribir_markdown(resultados, totales)
                raise
            except Exception as e:
                error = repr(e)
                print(f"  [{hms()}] ERROR: {error}")

            elapsed = time.time() - t0

            if out is not None:
                this_cost = costo_usd(out["usage"])
                print(f"  [{hms()}] Listo: iters={out['iterations']}  "
                      f"tools={len(out['tool_calls'])}  "
                      f"in={out['usage']['input_tokens']}  "
                      f"out={out['usage']['output_tokens']}  "
                      f"costo=${this_cost:.4f}  "
                      f"t={elapsed:.1f}s")
                totales["input_tokens"] += out["usage"]["input_tokens"]
                totales["output_tokens"] += out["usage"]["output_tokens"]
                totales["costo_usd"] += this_cost

                resultados.append({
                    "escenario": esc,
                    "consulta_id": cons["id"],
                    "query": query,
                    "iterations": out["iterations"],
                    "stop_reason": out["stop_reason"],
                    "tool_calls": out["tool_calls"],
                    "final_text": out["final_text"],
                    "usage": out["usage"],
                    "costo_usd": this_cost,
                    "elapsed_s": elapsed,
                    "error": None,
                })
            else:
                resultados.append({
                    "escenario": esc,
                    "consulta_id": cons["id"],
                    "query": query,
                    "error": error,
                    "elapsed_s": elapsed,
                })

            # PERSISTENCIA INCREMENTAL: guardar tras CADA consulta.
            guardar_estado(resultados, totales)
            escribir_markdown(resultados, totales)

    # Resumen final
    print("\n" + "=" * 70)
    print("TOTALES")
    print(f"  Tokens input:  {totales['input_tokens']:,}")
    print(f"  Tokens output: {totales['output_tokens']:,}")
    print(f"  Costo total:   ${totales['costo_usd']:.4f} USD")
    print(f"  Logs:          {LOG_MD}")
    print(f"                 {LOG_JSON}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Batería interrumpida. Estado parcial guardado en logs/.")
        sys.exit(1)
