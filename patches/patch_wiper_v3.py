from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"

# ---------------------------------------------------------------------------
# Monster8 Wiper V3
# - Stay inside Wiper Setup after every calibration action.
# - Z Down / Z Up move ONLY Z while already over the wiper; no G27, no XY park,
#   no return to X0/Y0 on every 0.05mm nudge.
# - Allow contact calibration below Z4.0 because the machine's actual probe / Z
#   reference can place the physical 4.8mm rubber top at a lower displayed Z.
# - Keep the proven one-button 240C Test Hot Wipe and all prior safety guards.
# ---------------------------------------------------------------------------

s = g28.read_text()

old = '''static float m8_clamp_z(const float z) {\n  return z < 4.00f ? 4.00f : (z > 8.00f ? 8.00f : z);\n}\n'''
new = '''static float m8_clamp_z(const float z) {\n  return z < 0.50f ? 0.50f : (z > 8.00f ? 8.00f : z);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V3: old Z clamp not found")
s = s.replace(old, new, 1)

old = '''void m8_wiper_queue_z_down() {\n  m8_wiper_z = m8_clamp_z(m8_wiper_z - 0.05f);\n  m8_wiper_queue_go_z();\n}\n\nvoid m8_wiper_queue_z_up() {\n  m8_wiper_z = m8_clamp_z(m8_wiper_z + 0.05f);\n  m8_wiper_queue_go_z();\n}\n'''
new = '''static bool m8_wiper_is_at_cal_xy() {\n  return ABS(current_position.x + 30.0f) <= 1.0f\n      && ABS(current_position.y + 30.0f) <= 1.0f;\n}\n\nvoid m8_wiper_queue_z_down() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy()) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z - 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z down 0.05"), 0);\n}\n\nvoid m8_wiper_queue_z_up() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy()) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z + 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z up 0.05"), 0);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V3: old Z up/down wrappers not found")
s = s.replace(old, new, 1)
g28.write_text(s)

s = menu.read_text()
old_helpers = '''static void m8_wiper_align_center() { m8_wiper_queue_align_center(); ui.return_to_status(); }\nstatic void m8_wiper_return_zero() { m8_wiper_queue_return_zero(); ui.return_to_status(); }\nstatic void m8_wiper_go_contact() { m8_wiper_queue_go_z(); ui.return_to_status(); }\nstatic void m8_wiper_z_down() { m8_wiper_queue_z_down(); ui.return_to_status(); }\nstatic void m8_wiper_z_up() { m8_wiper_queue_z_up(); ui.return_to_status(); }\nstatic void m8_wiper_test_hot() { m8_wiper_queue_test(); ui.return_to_status(); }\n'''
new_helpers = '''static void m8_wiper_align_center() { m8_wiper_queue_align_center(); }\nstatic void m8_wiper_return_zero() { m8_wiper_queue_return_zero(); }\nstatic void m8_wiper_go_contact() { m8_wiper_queue_go_z(); }\nstatic void m8_wiper_z_down() { m8_wiper_queue_z_down(); }\nstatic void m8_wiper_z_up() { m8_wiper_queue_z_up(); }\nstatic void m8_wiper_test_hot() { m8_wiper_queue_test(); }\n'''
if old_helpers not in s:
    raise SystemExit("Wiper V3: menu callback block not found")
s = s.replace(old_helpers, new_helpers, 1)

old_range = 'EDIT_ITEM_F(float42_52, F("Wiper Z mm"), &m8_wiper_z, 4.00f, 8.00f);'
new_range = 'EDIT_ITEM_F(float42_52, F("Wiper Z mm"), &m8_wiper_z, 0.50f, 8.00f);'
if old_range not in s:
    raise SystemExit("Wiper V3: Wiper Z menu range not found")
s = s.replace(old_range, new_range, 1)

# Add a short usage hint to make the calibration sequence obvious.
hint_anchor = '  STATIC_ITEM_F(F("Sweep Y-39 to Y-21"));\n'
if hint_anchor not in s:
    raise SystemExit("Wiper V3: menu hint anchor missing")
if 'STATIC_ITEM_F(F("Go Wiper Z then nudge"));' not in s:
    s = s.replace(hint_anchor, hint_anchor + '  STATIC_ITEM_F(F("Go Wiper Z then nudge"));\n', 1)
menu.write_text(s)

# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------
g28_text = g28.read_text()
menu_text = menu.read_text()
bed_text = bed.read_text()

for required in [
    'return z < 0.50f ? 0.50f : (z > 8.00f ? 8.00f : z);',
    'static bool m8_wiper_is_at_cal_xy()',
    'Go to Wiper Z first',
    'm8_run_dynamic_z_now();',
    'constexpr int16_t TEST_TEMP = 240;',
    'Test wipe done - heater off',
    'int16_t m8_auto_prime_length = 60;',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper V3 runtime guard missing: {required}")

for required in [
    'EDIT_ITEM_F(float42_52, F("Wiper Z mm"), &m8_wiper_z, 0.50f, 8.00f);',
    'static void m8_wiper_z_down() { m8_wiper_queue_z_down(); }',
    'static void m8_wiper_z_up() { m8_wiper_queue_z_up(); }',
    'STATIC_ITEM_F(F("Go Wiper Z then nudge"));',
]:
    if required not in menu_text:
        raise SystemExit(f"Wiper V3 menu guard missing: {required}")

if 'm8_wiper_z_down() { m8_wiper_queue_z_down(); ui.return_to_status(); }' in menu_text:
    raise SystemExit("Wiper V3: Z Down still exits Wiper Setup")
if 'm8_wiper_z_up() { m8_wiper_queue_z_up(); ui.return_to_status(); }' in menu_text:
    raise SystemExit("Wiper V3: Z Up still exits Wiper Setup")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper V3 bed regression guard failed: {required}")

print("Monster8 Wiper V3: menu stays open, direct 0.05mm Z nudges at wiper, Z range 0.50-8.00mm")
