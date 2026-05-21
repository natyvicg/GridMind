"""
test_validacion_umbrales.py — Verifica la validación de umbrales en
get_voltage_violations.

Casos de prueba:
  1. Default (sin args) → sin warning, sin error.
  2. v_max=1.25415 (valor observado, no umbral) → debe emitir warning.
  3. v_min=0.80 (umbral inusualmente bajo) → debe emitir warning.
  4. v_min=1.10, v_max=1.05 (invertidos) → debe devolver error duro.
  5. v_min=0.95, v_max=1.05 explícitos (correctos) → sin warning.

No requiere API key ni red real. Monkey-patchea _STATE con una red
mínima construida en memoria.

Uso:
    python test_validacion_umbrales.py
"""

import sys
import pandas as pd
import pandapower as pp

# Stub red_cr_loader para que tools.py importe sin archivos CR
class _StubMod:
    def cargar_red_cr(self, escenario):
        return None
sys.modules.setdefault("red_cr_loader", _StubMod())

import tools  # noqa: E402

# Red mínima con tensiones controladas para los tests
net = pp.create_empty_network()
b1 = pp.create_bus(net, vn_kv=110)
b2 = pp.create_bus(net, vn_kv=110)
b3 = pp.create_bus(net, vn_kv=110)
pp.create_ext_grid(net, b1)
pp.create_load(net, b2, p_mw=10)
pp.create_load(net, b3, p_mw=5)
pp.create_line_from_parameters(net, b1, b2, length_km=10, r_ohm_per_km=0.1,
                                x_ohm_per_km=0.4, c_nf_per_km=10, max_i_ka=1)
pp.create_line_from_parameters(net, b2, b3, length_km=10, r_ohm_per_km=0.1,
                                x_ohm_per_km=0.4, c_nf_per_km=10, max_i_ka=1)
pp.runpp(net)

tools._STATE["net"] = net
tools._STATE["current_network_name"] = "TEST"

print("=" * 70)
print("Test 1: defaults (omitidos) — esperamos sin warning")
print("=" * 70)
r = tools.get_voltage_violations()
print(f"  n_violations: {r['n_violations_total']}")
print(f"  warning: {r.get('warning', '(ninguno)')}")
assert "warning" not in r, "FALLO: no debería haber warning"
print("  OK\n")

print("=" * 70)
print("Test 2: v_max=1.25415 (valor observado usado como umbral por error)")
print("=" * 70)
r = tools.get_voltage_violations(v_max=1.25415)
print(f"  warning: {r.get('warning', '(ninguno)')}")
assert "warning" in r, "FALLO: debería haber warning"
assert "v_max" in r["warning"], "FALLO: el warning debería mencionar v_max"
print("  OK\n")

print("=" * 70)
print("Test 3: v_min=0.80 (umbral inusualmente bajo)")
print("=" * 70)
r = tools.get_voltage_violations(v_min=0.80)
print(f"  warning: {r.get('warning', '(ninguno)')}")
assert "warning" in r, "FALLO: debería haber warning"
assert "v_min" in r["warning"], "FALLO: el warning debería mencionar v_min"
print("  OK\n")

print("=" * 70)
print("Test 4: v_min=1.10, v_max=1.05 (invertidos)")
print("=" * 70)
r = tools.get_voltage_violations(v_min=1.10, v_max=1.05)
print(f"  error: {r.get('error', '(ninguno)')}")
assert "error" in r, "FALLO: debería haber error"
assert "v_min" in r["error"] and "v_max" in r["error"], \
    "FALLO: el error debería mencionar v_min y v_max"
print("  OK\n")

print("=" * 70)
print("Test 5: v_min=0.95, v_max=1.05 explícitos (correctos)")
print("=" * 70)
r = tools.get_voltage_violations(v_min=0.95, v_max=1.05)
print(f"  n_violations: {r['n_violations_total']}")
print(f"  warning: {r.get('warning', '(ninguno)')}")
assert "warning" not in r, "FALLO: no debería haber warning"
print("  OK\n")

print("=" * 70)
print("TODOS LOS TESTS PASARON ✅")
print("=" * 70)
