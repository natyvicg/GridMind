"""
ejecutar_escenarios_ieee14.py
================
Ejecuta los escenarios IEEE 14 y genera documentación visual.

Ejecuta los 4 escenarios IEEE 14 definidos en escenarios.py,
genera diagramas unifilares coloreados por violación, y exporta una
tabla-resumen en Excel para documentación del TFG.

Salidas generadas (en el directorio de trabajo):
    - unifilar_original.png
    - unifilar_base.png
    - unifilar_subtension.png
    - unifilar_sobrecarga.png
    - resumen_escenarios_ieee14.xlsx

Uso: ejecutar directamente en Spyder (F5) con este archivo y
escenarios.py en la misma carpeta.
"""
import json
import pandas as pd
import pandapower.plotting as plot
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from escenarios import (
    construir_escenarios_red,
    V_MIN, V_MAX, LOADING_MAX,
)


# ==============================================================
# VISUALIZACIÓN — diagrama unifilar con código de colores
# ==============================================================
def color_bus(v_pu):
    """Color de barra según tensión."""
    if v_pu < V_MIN or v_pu > V_MAX:
        return '#e74c3c'      # rojo — violación
    elif v_pu < 0.97 or v_pu > 1.03:
        return '#f39c12'      # naranja — borderline
    else:
        return '#27ae60'      # verde — OK


def color_line(loading_pct):
    """Color de línea/trafo según cargabilidad."""
    if loading_pct > LOADING_MAX:
        return '#e74c3c'      # rojo — sobrecarga
    elif loading_pct > 80:
        return '#f39c12'      # naranja — cercano al límite
    else:
        return '#27ae60'      # verde — OK


def get_bus_coords(net, bus_idx):
    """Extrae coordenadas (x, y) del campo geo (GeoJSON) de un bus."""
    geo_str = net.bus.loc[bus_idx, 'geo']
    if geo_str is None:
        return None, None
    coords = json.loads(geo_str)['coordinates']
    return coords[0], coords[1]


def dibujar_unifilar(net, titulo, archivo_salida):
    """Genera el diagrama unifilar coloreado de una red."""
    # Colores
    bus_colors = [color_bus(v) for v in net.res_bus.vm_pu]
    line_colors = [color_line(l) for l in net.res_line.loading_percent]
    # Trafos: cargabilidad se obtiene de res_trafo.loading_percent
    trafo_colors = [color_line(l) for l in net.res_trafo.loading_percent]

    # Considerar líneas fuera de servicio (las mostramos en gris punteado)
    in_service_lines = net.line.in_service.values
    line_styles = ['-' if s else '--' for s in in_service_lines]

    # Colecciones de pandapower
    bc = plot.create_bus_collection(
        net, buses=net.bus.index, color=bus_colors,
        size=0.08, zorder=3
    )
    lc = plot.create_line_collection(
        net, lines=net.line.index, color=line_colors,
        use_bus_geodata=True, linewidths=2.5, zorder=1
    )

    # Figura
    fig, ax = plt.subplots(figsize=(11, 8))
    plot.draw_collections([lc, bc], ax=ax)

    # Trafos: dibujar como líneas punteadas entre hv_bus y lv_bus
    # (más legible que las rueditas de pandapower)
    for idx in net.trafo.index:
        hv, lv = net.trafo.loc[idx, 'hv_bus'], net.trafo.loc[idx, 'lv_bus']
        x1, y1 = get_bus_coords(net, hv)
        x2, y2 = get_bus_coords(net, lv)
        if x1 is None or x2 is None:
            continue
        color = trafo_colors[list(net.trafo.index).index(idx)]
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=2.0,
                linestyle='--', zorder=1, alpha=0.8)
        # Marcador T en el medio para identificar que es trafo
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.scatter([mx], [my], marker='s', s=50, c='white',
                   edgecolors=color, linewidths=1.5, zorder=2)
        ax.annotate('T', xy=(mx, my), ha='center', va='center',
                    fontsize=7, fontweight='bold', color=color, zorder=3)

    # Anotaciones sobre cada barra (número + V)
    for idx in net.bus.index:
        x, y = get_bus_coords(net, idx)
        if x is None:
            continue
        v = net.res_bus.loc[idx, 'vm_pu']
        ax.annotate(
            f"B{idx+1}\n{v:.3f}",
            xy=(x, y), xytext=(8, 8),
            textcoords='offset points',
            fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                      edgecolor='gray', alpha=0.8)
        )

    # Etiquetas sobre líneas con cargabilidad > 80%
    for idx in net.line.index:
        if not net.line.loc[idx, 'in_service']:
            continue
        loading = net.res_line.loc[idx, 'loading_percent']
        if loading > 80:
            frm = net.line.loc[idx, 'from_bus']
            to = net.line.loc[idx, 'to_bus']
            x1, y1 = get_bus_coords(net, frm)
            x2, y2 = get_bus_coords(net, to)
            if x1 is not None and x2 is not None:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                ax.annotate(
                    f"{loading:.0f}%",
                    xy=(mx, my),
                    fontsize=7, fontweight='bold',
                    color='darkred',
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='yellow',
                              edgecolor='red', alpha=0.9)
                )

    # Leyenda
    legend_elements = [
        Patch(facecolor='#27ae60', label='OK (V ∈ [0.95, 1.05], carga < 80%)'),
        Patch(facecolor='#f39c12', label='Borderline (V cerca límite, carga 80-100%)'),
        Patch(facecolor='#e74c3c', label='Violación (V fuera de rango, carga > 100%)'),
    ]
    ax.legend(handles=legend_elements, loc='lower right',
              fontsize=9, framealpha=0.9)

    ax.set_title(titulo, fontsize=13, fontweight='bold')
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(archivo_salida, dpi=140, bbox_inches='tight')
    plt.close()
    print(f"  → {archivo_salida}")


# ==============================================================
# REPORTE — tabla resumen en Excel
# ==============================================================
def generar_tabla_resumen(resultados):
    """
    Construye un DataFrame con el resumen de los 4 escenarios
    usando el ground truth ya calculado por escenarios.py.

    Formato pensado para ir directamente a los anexos del TFG.
    """
    filas = []
    for nombre, data in resultados.items():
        net = data['net']
        gt = data['gt']
        if gt is None:
            continue

        # Listar buses/líneas en violación
        buses_sub = ", ".join(
            [f"B{i+1}" for i in gt['buses_subtension']]
        ) if gt['n_subtension'] else "—"

        buses_sobre = ", ".join(
            [f"B{i+1}" for i in gt['buses_sobretension']]
        ) if gt['n_sobretension'] else "—"

        lineas_sob = ", ".join([
            f"L{net.line.loc[i,'from_bus']+1}-{net.line.loc[i,'to_bus']+1}"
            for i in gt['lineas_sobrecarga']
        ]) if gt['n_lineas_sobrecarga'] else "—"

        filas.append({
            'Escenario': nombre,
            'Vmin [pu]': gt['v_min_pu'],
            'Vmax [pu]': gt['v_max_pu'],
            'Cargabilidad máx línea [%]': gt['max_loading_linea_pct'],
            'N° barras subtensión': gt['n_subtension'],
            'Buses en subtensión': buses_sub,
            'N° barras sobretensión': gt['n_sobretension'],
            'Buses en sobretensión': buses_sobre,
            'N° líneas sobrecarga': gt['n_lineas_sobrecarga'],
            'Líneas en sobrecarga': lineas_sob,
        })
    return pd.DataFrame(filas)


# ==============================================================
# MAIN
# ==============================================================
def main():
    print("=" * 65)
    print("IEEE 14 — Escenarios controlados con violaciones inducidas")
    print("=" * 65)

    # Paso 1: construir los 4 escenarios
    print("\n[1/4] Construyendo escenarios...")
    resultados = construir_escenarios_red("IEEE_14")
    for nombre, data in resultados.items():
        viable = data['meta'].get('viable', True)
        estado = "viable" if viable else "NO viable"
        print(f"  ✓ Escenario '{nombre}' construido ({estado})")

    # Paso 2: imprimir resumen por escenario
    print("\n[2/4] Resumen de violaciones operativas...")
    for nombre, data in resultados.items():
        gt = data['gt']
        if gt is None:
            print(f"\n  [{nombre}] — no convergió")
            continue
        print(f"\n  [{nombre}]")
        print(f"    Vmin = {gt['v_min_pu']:.4f} pu")
        print(f"    Vmax = {gt['v_max_pu']:.4f} pu")
        print(f"    Cargabilidad máx línea = {gt['max_loading_linea_pct']:.2f}%")
        print(f"    Barras subtensión: {gt['n_subtension']}")
        print(f"    Barras sobretensión: {gt['n_sobretension']}")
        print(f"    Líneas sobrecarga: {gt['n_lineas_sobrecarga']}")

    # Paso 3: generar diagramas unifilares
    print("\n[3/4] Generando diagramas unifilares coloreados...")
    titulos = {
        'ORIGINAL':   'IEEE 14 — Escenario ORIGINAL (CDF oficial AEP Test System)',
        'BASE':       'IEEE 14 — Escenario BASE (calibrado, control negativo)',
        'SUBTENSIÓN': 'IEEE 14 — Escenario SUBTENSIÓN (calibrado)',
        'SOBRECARGA': 'IEEE 14 — Escenario SOBRECARGA (calibrado, N-1 + cargas x1.3)',
    }
    for nombre, data in resultados.items():
        net = data['net']
        titulo = titulos.get(nombre, f'IEEE 14 — {nombre}')
        archivo = f"unifilar_{nombre.lower().replace('ó', 'o')}.png"
        dibujar_unifilar(net, titulo, archivo)

    # Paso 4: exportar tabla resumen a Excel
    print("\n[4/4] Exportando tabla resumen a Excel...")
    tabla = generar_tabla_resumen(resultados)
    archivo_excel = "resumen_escenarios_ieee14.xlsx"
    with pd.ExcelWriter(archivo_excel, engine='openpyxl') as writer:
        tabla.to_excel(writer, sheet_name='Resumen', index=False)
    print(f"  → {archivo_excel}")

    # Cierre
    print("\n" + "=" * 65)
    print("ESCENARIOS IEEE 14 COMPLETADOS")
    print("=" * 65)
    print("\nTabla resumen:")
    print(tabla.to_string(index=False))


if __name__ == "__main__":
    main()
