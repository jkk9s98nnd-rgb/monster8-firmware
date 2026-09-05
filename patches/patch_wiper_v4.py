from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"


def find_function_end(text: str, signature: str) -> int:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Wiper V4: function not found: {signature}")
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f"Wiper V4: opening brace not found: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    raise SystemExit(f"Wiper V4: closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# Monster8 Wiper V4
# Hardware test proved the physical brush contact height is Z4.00 and normal
# LCD Move Z reaches it correctly. The old wiper helper issued nested G-code
# from an LCD callback and the machine stayed at the safe-lift height (~Z22).
# Use Marlin's native blocking motion calls instead, exactly like the normal
# motion system, so the nozzle must physically reach the requested Z.
# ---------------------------------------------------------------------------
s = g28.read_text()

# Make the motion API unconditionally visible in this translation unit.
inc_anchor = '#include "../../module/stepper.h" // for various\n'
if inc_anchor not in s:
    raise SystemExit("Wiper V4: stepper include anchor missing")
if 'Monster8 direct wiper motion' not in s:
    s = s.replace(
        inc_anchor,
        inc_anchor + '#include "../../module/motion.h" // Monster8 direct wiper motion\n',
        1,
    )

# Calibrated physical brush contact from the printer.
if 'float m8_wiper_z = 6.00f;' not in s:
    raise SystemExit("Wiper V4: expected prior Wiper Z default 6.00 not found")
s = s.replace('float m8_wiper_z = 6.00f;', 'float m8_wiper_z = 4.00f;', 1)

# Replace nested G1 Z execution with native blocking Z motion.
old_helper = '''static void m8_run_dynamic_z_now() {\n  char cmd[32];\n  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%.2f F300"), double(m8_clamp_z(m8_wiper_z)));\n  gcode.process_subcommands_now(cmd);\n}\n'''
new_helper = '''static void m8_run_dynamic_z_now() {\n  const float target_z = m8_clamp_z(m8_wiper_z);\n  do_blocking_move_to_z(target_z, 5.0f); // Same native motion path proven by LCD Move Z\n}\n'''
if old_helper not in s:
    raise SystemExit("Wiper V4: old dynamic-Z helper not found")
s = s.replace(old_helper, new_helper, 1)

# Go to Wiper Z must also avoid G27 / nested G-code for the calibration move.
old_go = '''void m8_wiper_queue_go_z() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z);\n  gcode.process_subcommands_now(F("M420 S0\\nG27\\nG90\\nG1 X-30 Y-30 F2400"));\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Check wiper contact"), 0);\n}\n'''
new_go = '''void m8_wiper_queue_go_z() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z);\n  TERN_(HAS_LEVELING, set_bed_leveling_enabled(false));\n\n  // Lift only when needed, move over the wiper, then use direct native Z motion\n  // to the calibrated contact height. No G27 and no nested G1 Z here.\n  const float safe_z = current_position.z < 10.0f ? 10.0f : current_position.z;\n  if (current_position.z < safe_z) do_blocking_move_to_z(safe_z, 10.0f);\n  do_blocking_move_to_xy(-30.0f, -30.0f, 40.0f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("At Wiper Z - nudge if needed"), 0);\n}\n'''
if old_go not in s:
    raise SystemExit("Wiper V4: prior Go to Wiper Z function not found")
s = s.replace(old_go, new_go, 1)

# Make nudges derive from the ACTUAL current Z, not only the stored value.
old_down = '''void m8_wiper_queue_z_down() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy()) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z - 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z down 0.05"), 0);\n}\n'''
new_down = '''void m8_wiper_queue_z_down() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy() || ABS(current_position.z - m8_wiper_z) > 0.25f) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(current_position.z - 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z down 0.05"), 0);\n}\n'''
if old_down not in s:
    raise SystemExit("Wiper V4: prior Z Down function not found")
s = s.replace(old_down, new_down, 1)

old_up = '''void m8_wiper_queue_z_up() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy()) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z + 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z up 0.05"), 0);\n}\n'''
new_up = '''void m8_wiper_queue_z_up() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  if (!m8_wiper_is_at_cal_xy() || ABS(current_position.z - m8_wiper_z) > 0.25f) {\n    ui.set_status(F("Go to Wiper Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(current_position.z + 0.05f);\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Wiper Z up 0.05"), 0);\n}\n'''
if old_up not in s:
    raise SystemExit("Wiper V4: prior Z Up function not found")
s = s.replace(old_up, new_up, 1)

# Replace automatic wipe movement with native blocking moves too, so Test,
# before-print, and after-print all use the same proven physical motion path.
run_sig = 'static void m8_wiper_run_now(const bool restore_leveling)'
run_start = s.find(run_sig)
run_end = find_function_end(s, run_sig)
new_run = '''static void m8_wiper_run_now(const bool restore_leveling) {\n  const float wz = m8_clamp_z(m8_wiper_z);\n  const int16_t passes = m8_clamp_passes(m8_wiper_passes);\n  const float wipe_fr = float(m8_clamp_speed(m8_wiper_speed));\n\n  ui.set_status(F("Nozzle Wiping"), 0);\n  TERN_(HAS_LEVELING, set_bed_leveling_enabled(false));\n\n  const float safe_z = current_position.z < M8_WIPER_SAFE_Z ? M8_WIPER_SAFE_Z : current_position.z;\n  if (current_position.z < safe_z) do_blocking_move_to_z(safe_z, 10.0f);\n  do_blocking_move_to_xy(M8_WIPER_X, M8_WIPER_Y_START, 40.0f);\n  do_blocking_move_to_z(wz, 5.0f);\n\n  for (int16_t i = 0; i < passes; ++i)\n    do_blocking_move_to_y((i & 1) ? M8_WIPER_Y_START : M8_WIPER_Y_END, wipe_fr);\n\n  do_blocking_move_to_z(M8_WIPER_SAFE_Z, 10.0f);\n  do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);\n\n  if (restore_leveling) TERN_(HAS_LEVELING, set_bed_leveling_enabled(true));\n}\n'''
s = s[:run_start] + new_run + s[run_end + 1:]

# Simplify manual Test Hot Wipe so it uses the exact same direct-motion routine.
test_sig = 'void m8_wiper_queue_test()'
test_start = s.find(test_sig)
test_end = find_function_end(s, test_sig)
new_test = '''void m8_wiper_queue_test() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n\n  constexpr int16_t TEST_TEMP = 240;\n  ui.set_status(F("Heating to 240 for wipe"), 0);\n  thermalManager.setTargetHotend(TEST_TEMP, 0);\n  (void)thermalManager.wait_for_hotend(0, false);\n\n  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) {\n    thermalManager.setTargetHotend(0, 0);\n    ui.set_status(F("Wiper heat failed"), 0);\n    return;\n  }\n\n  m8_wiper_run_now(false);\n  thermalManager.setTargetHotend(0, 0);\n  ui.set_status(F("Test wipe done - heater off"), 0);\n}\n'''
s = s[:test_start] + new_test + s[test_end + 1:]

g28.write_text(s)

# Update the on-screen hint to show the confirmed contact value.
s = menu.read_text()
old_hint = '  STATIC_ITEM_F(F("Go Wiper Z then nudge"));\n'
new_hint = '  STATIC_ITEM_F(F("Contact calibrated Z4.00"));\n'
if old_hint not in s:
    raise SystemExit("Wiper V4: V3 usage hint not found")
s = s.replace(old_hint, new_hint, 1)
menu.write_text(s)

# ---------------------------------------------------------------------------
# Regression guards. Refuse to build if any proven Monster8 behavior moved.
# ---------------------------------------------------------------------------
g28_text = g28.read_text()
menu_text = menu.read_text()
bed_text = bed.read_text()

for required in [
    'float m8_wiper_z = 4.00f;',
    'do_blocking_move_to_z(target_z, 5.0f);',
    'do_blocking_move_to_xy(-30.0f, -30.0f, 40.0f);',
    'do_blocking_move_to_xy(M8_WIPER_X, M8_WIPER_Y_START, 40.0f);',
    'do_blocking_move_to_y((i & 1) ? M8_WIPER_Y_START : M8_WIPER_Y_END, wipe_fr);',
    'm8_wiper_run_now(false);',
    'constexpr int16_t TEST_TEMP = 240;',
    'Test wipe done - heater off',
    'int16_t m8_auto_prime_length = 60;',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper V4 runtime guard missing: {required}")

if 'snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%.2f F300")' in g28_text:
    raise SystemExit("Wiper V4: old nested G1 Z helper still present")

for required in [
    'F("Wiper Enabled")',
    'F("Go to Wiper Z")',
    'F("Z Down 0.05")',
    'F("Z Up 0.05")',
    'F("Test Hot Wipe")',
    'STATIC_ITEM_F(F("Contact calibrated Z4.00"));',
]:
    if required not in menu_text:
        raise SystemExit(f"Wiper V4 menu guard missing: {required}")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper V4 bed regression guard failed: {required}")

print("Monster8 Wiper V4: direct blocking Z/XY wiping with calibrated Z4.00 contact")
