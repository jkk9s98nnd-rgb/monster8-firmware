from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
g27 = root / "src/gcode/feature/pause/G27.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    s = path.read_text()
    if old not in s:
        raise SystemExit(f"{label}: expected source not found in {path}")
    path.write_text(s.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1) G27 must understand the Monster8 virtual/manual XY reference.
# Stock Marlin requires every axis to be conventionally homed before parking.
# This machine deliberately has no X/Y switches, so when Ignore XY Home is ON,
# require only a trusted Z axis. This fixes park use from Wiper Setup, Stop,
# Pause, and normal print completion without ever attempting X/Y homing.
# ---------------------------------------------------------------------------
s = g27.read_text()
inc = '#include "../../../module/motion.h"\n'
if inc not in s:
    raise SystemExit("Wiper V2: G27 motion include missing")
if 'extern bool m8_ignore_xy_home;' not in s:
    s = s.replace(inc, inc + '\nextern bool m8_ignore_xy_home;\n', 1)
old = '''  // Don't allow nozzle parking without homing first\n  if (homing_needed_error()) return;\n'''
new = '''  // Monster8 has a manual/virtual X0/Y0 and no X/Y switches. When the\n  // Ignore XY Home guard is ON, only Z must be physically homed/trusted.\n  // With the guard OFF retain stock Marlin all-axis homing requirements.\n  if (m8_ignore_xy_home) {\n    if (homing_needed_error(_BV(Z_AXIS))) return;\n  }\n  else if (homing_needed_error()) return;\n'''
if old not in s:
    raise SystemExit("Wiper V2: stock G27 homing check missing")
s = s.replace(old, new, 1)
g27.write_text(s)


# ---------------------------------------------------------------------------
# 2) Make every Wiper Setup action synchronous and deterministic. The prior
# revision queued several commands from LCD callbacks; on the physical printer
# these controls appeared to do nothing. process_subcommands_now executes each
# calibration action immediately and keeps the LCD/thermal idle loop alive.
# ---------------------------------------------------------------------------
s = g28.read_text()

old = '''static void m8_queue_dynamic_z() {\n  char cmd[32];\n  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%.2f F300"), double(m8_clamp_z(m8_wiper_z)));\n  queue.enqueue_one_now(cmd);\n}\n'''
new = '''static void m8_run_dynamic_z_now() {\n  char cmd[32];\n  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%.2f F300"), double(m8_clamp_z(m8_wiper_z)));\n  gcode.process_subcommands_now(cmd);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V2: dynamic-Z helper missing")
s = s.replace(old, new, 1)

old = '''void m8_wiper_queue_align_center() {\n  queue.enqueue_one_now(F("M420 S0"));\n  queue.enqueue_one_now(F("G27"));\n  queue.enqueue_one_now(F("G90"));\n  queue.enqueue_one_now(F("G1 X-30 Y-30 F2400"));\n  queue.enqueue_one_now(F("G1 Z10 F600"));\n  ui.set_status(F("Center wiper under nozzle"), 0);\n}\n'''
new = '''void m8_wiper_queue_align_center() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  ui.set_status(F("Moving to wiper center"), 0);\n  gcode.process_subcommands_now(F("M420 S0\\nG27\\nG90\\nG1 X-30 Y-30 F2400\\nG1 Z10 F600"));\n  ui.set_status(F("Center wiper under nozzle"), 0);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V2: align-center function missing")
s = s.replace(old, new, 1)

old = '''void m8_wiper_queue_return_zero() {\n  queue.enqueue_one_now(F("M420 S0"));\n  queue.enqueue_one_now(F("G27"));\n  ui.set_status(F("Wiper setup parked"), 0);\n}\n'''
new = '''void m8_wiper_queue_return_zero() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  gcode.process_subcommands_now(F("M420 S0\\nG27"));\n  ui.set_status(F("Wiper setup parked"), 0);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V2: return-zero function missing")
s = s.replace(old, new, 1)

old = '''void m8_wiper_queue_go_z() {\n  m8_wiper_z = m8_clamp_z(m8_wiper_z);\n  queue.enqueue_one_now(F("M420 S0"));\n  queue.enqueue_one_now(F("G27"));\n  queue.enqueue_one_now(F("G90"));\n  queue.enqueue_one_now(F("G1 X-30 Y-30 F2400"));\n  m8_queue_dynamic_z();\n  ui.set_status(F("Check wiper contact"), 0);\n}\n'''
new = '''void m8_wiper_queue_go_z() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n  m8_wiper_z = m8_clamp_z(m8_wiper_z);\n  gcode.process_subcommands_now(F("M420 S0\\nG27\\nG90\\nG1 X-30 Y-30 F2400"));\n  m8_run_dynamic_z_now();\n  ui.set_status(F("Check wiper contact"), 0);\n}\n'''
if old not in s:
    raise SystemExit("Wiper V2: go-contact function missing")
s = s.replace(old, new, 1)

# Z Up/Down remain small wrappers around go_z, which is now synchronous.

old_start = '''void m8_wiper_queue_test() {\n  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) {\n    ui.set_status(F("Heat nozzle above 170C"), 0);\n    return;\n  }\n\n  const int16_t passes = m8_clamp_passes(m8_wiper_passes);\n  const int16_t wipe_f = m8_clamp_speed(m8_wiper_speed) * 60;\n  char cmd[32];\n\n  queue.enqueue_one_now(F("M420 S0"));\n  queue.enqueue_one_now(F("G27"));\n  queue.enqueue_one_now(F("G90"));\n  queue.enqueue_one_now(F("G1 X-30 Y-39 F2400"));\n  m8_queue_dynamic_z();\n\n  for (int16_t i = 0; i < passes; ++i) {\n    const int y = (i & 1) ? -39 : -21;\n    snprintf_P(cmd, sizeof(cmd), PSTR("G1 Y%i F%i"), y, int(wipe_f));\n    queue.enqueue_one_now(cmd);\n  }\n\n  queue.enqueue_one_now(F("G1 Z10 F600"));\n  queue.enqueue_one_now(F("G1 X0 Y0 F2400"));\n  ui.set_status(F("Test wipe complete"), 0);\n}\n'''
new_start = '''void m8_wiper_queue_test() {\n  if (!axis_is_trusted(Z_AXIS)) {\n    ui.set_status(F("Home Z first"), 0);\n    return;\n  }\n\n  // One-button test requested for the physical Monster8:\n  // heat -> wait -> wipe -> lift -> X0/Y0 -> heater OFF.\n  // Test is intentionally independent of the Wiper Enabled checkbox.\n  constexpr int16_t TEST_TEMP = 240;\n  ui.set_status(F("Heating to 240 for wipe"), 0);\n  thermalManager.setTargetHotend(TEST_TEMP, 0);\n  (void)thermalManager.wait_for_hotend(0, false);\n\n  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) {\n    thermalManager.setTargetHotend(0, 0);\n    ui.set_status(F("Wiper heat failed"), 0);\n    return;\n  }\n\n  const int16_t passes = m8_clamp_passes(m8_wiper_passes);\n  const int16_t wipe_f = m8_clamp_speed(m8_wiper_speed) * 60;\n  char cmd[32];\n\n  ui.set_status(F("Test nozzle wipe"), 0);\n  gcode.process_subcommands_now(F("M420 S0\\nG27\\nG90\\nG1 X-30 Y-39 F2400"));\n  m8_run_dynamic_z_now();\n\n  for (int16_t i = 0; i < passes; ++i) {\n    const int y = (i & 1) ? -39 : -21;\n    snprintf_P(cmd, sizeof(cmd), PSTR("G1 Y%i F%i"), y, int(wipe_f));\n    gcode.process_subcommands_now(cmd);\n  }\n\n  gcode.process_subcommands_now(F("G1 Z10 F600\\nG1 X0 Y0 F2400"));\n  thermalManager.setTargetHotend(0, 0);\n  ui.set_status(F("Test wipe done - heater off"), 0);\n}\n'''
if old_start not in s:
    raise SystemExit("Wiper V2: old Test Hot Wipe function missing")
s = s.replace(old_start, new_start, 1)

g28.write_text(s)


# ---------------------------------------------------------------------------
# Regression guards: do not allow this fix to disturb the proven mesh/XY zero,
# prime defaults, or wiper geometry.
# ---------------------------------------------------------------------------
g28_text = g28.read_text()
g27_text = g27.read_text()
menu_text = menu.read_text()
bed_text = bed.read_text()

for required in [
    'if (m8_ignore_xy_home)',
    'homing_needed_error(_BV(Z_AXIS))',
]:
    if required not in g27_text:
        raise SystemExit(f"Wiper V2 G27 guard missing: {required}")

for required in [
    'constexpr int16_t TEST_TEMP = 240;',
    'thermalManager.wait_for_hotend(0, false)',
    'Test wipe done - heater off',
    'gcode.process_subcommands_now(F("M420 S0\\nG27\\nG90\\nG1 X-30 Y-39 F2400"));',
    'float m8_wiper_z = 6.00f;',
    'int16_t m8_wiper_passes = 4;',
    'int16_t m8_auto_prime_length = 60;',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper V2 runtime guard missing: {required}")

for required in [
    'F("Wiper Enabled")',
    'F("Go to Wiper Z")',
    'F("Z Down 0.05")',
    'F("Z Up 0.05")',
    'F("Test Hot Wipe")',
]:
    if required not in menu_text:
        raise SystemExit(f"Wiper V2 menu guard missing: {required}")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper V2 bed regression: {required}")

print("Monster8 Wiper V2: fixed virtual-XY G27, synchronous calibration controls, and one-button 240C Test Hot Wipe")
