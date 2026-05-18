"""
probar_escenarios_genericos.py — Verificación de escenarios genéricos
=====================================================================
Ejecutar en Spyder para verificar que escenarios.py funciona
correctamente con IEEE 14 y con otra red a elección.

Salida: tabla de viabilidad + detalle de ground truth por escenario.
"""

from escenarios import construir_escenarios_red, construir_todos_ieee, resumen_viabilidad

# ── 1. Probar IEEE 14 (debe coincidir con escenarios curados) ──────────

print("=" * 70)
print("PRUEBA 1: IEEE 14 — Escenarios genéricos")
print("=" * 70)

res14 = construir_escenarios_red("IEEE_14")

for tipo, data in res14.items():
    m = data['meta']
    gt = data['gt']
    print(f"\n--- {tipo} ---")
    print(f"  Convergió: {m['converged']}")
    print(f"  Viable:    {m['viable']}")
    print(f"  Razón:     {m['razon']}")
    if gt:
        print(f"  V min:     {gt['v_min_pu']} pu")
        print(f"  V max:     {gt['v_max_pu']} pu")
        print(f"  Subtensión:  {gt['n_subtension']} barras → {gt['buses_subtension']}")
        print(f"  Sobretensión:{gt['n_sobretension']} barras → {gt['buses_sobretension']}")
        print(f"  Líneas >100%:{gt['n_lineas_sobrecarga']} → {gt['lineas_sobrecarga']}")
    if 'buses_afectados' in m:
        print(f"  Gens bajados (buses): {m['buses_afectados']}")
    if 'linea_desconectada' in m:
        print(f"  Línea desconectada: idx={m['linea_desconectada']} "
              f"(bus {m['linea_from_bus']}→{m['linea_to_bus']})")


# ── 2. Probar otra red (cambiar aquí si se desea) ─────────────────────

RED_PRUEBA = "IEEE_30"  # ← cambiar a "IEEE_118", "IEEE_200", etc.

print("\n")
print("=" * 70)
print(f"PRUEBA 2: {RED_PRUEBA} — Escenarios genéricos")
print("=" * 70)

res = construir_escenarios_red(RED_PRUEBA)

for tipo, data in res.items():
    m = data['meta']
    gt = data['gt']
    print(f"\n--- {tipo} ---")
    print(f"  Convergió: {m['converged']}")
    print(f"  Viable:    {m['viable']}")
    print(f"  Razón:     {m['razon']}")
    if gt:
        print(f"  V min:     {gt['v_min_pu']} pu")
        print(f"  V max:     {gt['v_max_pu']} pu")
        print(f"  Subtensión:  {gt['n_subtension']} barras")
        print(f"  Sobretensión:{gt['n_sobretension']} barras")
        print(f"  Líneas >100%:{gt['n_lineas_sobrecarga']}")
        print(f"  Trafos >100%:{gt.get('n_trafos_sobrecarga', 0)}")


# ── 3. (Opcional) Tabla completa de las 15 redes ─────────────────────
# Descomentar las siguientes líneas para correr TODAS las redes.
# Tarda ~30 segundos.

print("\n")
print("=" * 70)
print("TABLA COMPLETA DE VIABILIDAD — 15 redes IEEE")
print("=" * 70)
todos = construir_todos_ieee()
df = resumen_viabilidad(todos)
print(df.to_string(index=False))
df.to_excel("viabilidad_escenarios_ieee.xlsx", index=False)
print("\n→ Exportado a viabilidad_escenarios_ieee.xlsx")
