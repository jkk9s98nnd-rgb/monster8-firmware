from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
m109 = root / "src/gcode/temp/M104_M109.cpp"
core = root / "src/MarlinCore.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"

# ---------------------------------------------------------------------------
# Monster8 V7 Orca stop/start safety
#
# Hardware observations:
# - Stop Print could leave a queued G27 / stale prime handshake behind.
# - A new plain slicer G28 could therefore be followed by XY motion at low Z.
# - Auto-prime itself lowered to Z0.40 BEFORE traveling to X10/Y10.
#
# Safety rules enforced here:
# 1) A plain Orca G28 (filtered to Z-only) ALWAYS ends at safe Z10.
# 2) A new plain G28 clears stale heat/prime state; no wipe/prime may run until
#    the CURRENT print's M109 finishes successfully.
# 3) Prime travel goes to X10/Y10 at safe Z first, then lowers to Z0.40.
# 4) SD Stop clears normal + injected queues, cancels prime state, performs a
#    direct blocking Z lift, THEN parks XY at 0/0. No queued abort G27 remains.
# 5) An aborted M109 never marks the nozzle as ready for wipe/prime.
# ---------------------------------------------------------------------------

# --- G28: reset stale handshake and finish plain slicer home at safe Z10. ---
s = g28.read_text()
old = '''  if (m8_plain_slicer_home && m8_ignore_xy_home) {\n    m8_auto_prime_home_seen = true;\n    m8_auto_prime_done = false;\n    m8_auto_prime_try();\n  }\n'''
new = '''  if (m8_plain_slicer_home && m8_ignore_xy_home) {\n    // This is a NEW Orca print handshake. Never inherit a hot/prime-ready\n    // state from a stopped print. The current print must complete M109 first.\n    m8_auto_prime_heat_seen = false;\n    m8_auto_prime_home_seen = true;\n    m8_auto_prime_done = false;\n\n    // Z homing can finish close to the bed. Establish a hard safety invariant:\n    // no command after the slicer's plain G28 sees Z below 10mm.\n    if (axis_is_trusted(Z_AXIS) && current_position.z < 10.0f)\n      do_blocking_move_to_z(10.0f, 10.0f);\n  }\n'''
if old not in s:
    raise SystemExit("V7: plain G28 handshake block not found")
s = s.replace(old, new, 1)

# Prime positioning must happen at safe Z, not at first-layer Z.
prime_anchor = '''  // Clamp editable LCD values to the reserved safe prime strip.\n  const int16_t plen = m8_auto_prime_length < 20 ? 20 : (m8_auto_prime_length > 100 ? 100 : m8_auto_prime_length);\n'''
prime_new = '''  // Travel to the prime strip only while safely lifted. The previous sequence\n  // lowered to Z0.40 first and then crossed the bed, which can drag the nozzle.\n  const float m8_prime_safe_z = current_position.z < 10.0f ? 10.0f : current_position.z;\n  if (current_position.z < m8_prime_safe_z)\n    do_blocking_move_to_z(m8_prime_safe_z, 10.0f);\n  do_blocking_move_to_xy(10.0f, 10.0f, 40.0f);\n\n  // Clamp editable LCD values to the reserved safe prime strip.\n  const int16_t plen = m8_auto_prime_length < 20 ? 20 : (m8_auto_prime_length > 100 ? 100 : m8_auto_prime_length);\n'''
if prime_anchor not in s:
    raise SystemExit("V7: prime clamp anchor not found")
s = s.replace(prime_anchor, prime_new, 1)

old_prime = '    PSTR("G90\\nM83\\nG1 Z0.40 F600\\nG1 X10 Y10 F2400\\nG92 E0\\nG1 X%i E%i F600"),\n'
new_prime = '    PSTR("G90\\nM83\\nG1 Z0.40 F600\\nG92 E0\\nG1 X%i E%i F600"),\n'
if old_prime not in s:
    raise SystemExit("V7: unsafe prime travel string not found")
s = s.replace(old_prime, new_prime, 1)
g28.write_text(s)

# --- M109: only arm wipe/prime if the heat wait actually completed. ---
s = m109.read_text()
old = '''  if (isM109 && got_temp) {\n    (void)thermalManager.wait_for_hotend(target_extruder, no_wait_for_cooling);\n    if (target_extruder == 0 && temp >= EXTRUDE_MINTEMP) {\n      m8_auto_prime_heat_seen = true;\n      m8_auto_prime_try();\n    }\n    else if (temp < EXTRUDE_MINTEMP) {\n      m8_auto_prime_heat_seen = false;\n      m8_auto_prime_home_seen = false;\n      m8_auto_prime_done = false;\n    }\n  }\n'''
new = '''  if (isM109 && got_temp) {\n    const bool m8_heat_wait_ok = thermalManager.wait_for_hotend(target_extruder, no_wait_for_cooling);\n    if (m8_heat_wait_ok && target_extruder == 0 && temp >= EXTRUDE_MINTEMP\n        && thermalManager.degHotend(0) >= EXTRUDE_MINTEMP) {\n      m8_auto_prime_heat_seen = true;\n      m8_auto_prime_try();\n    }\n    else {\n      // Stop / M108 / failed heat wait must never fall through into a wipe or\n      // prime. The next plain G28 starts a completely fresh handshake.\n      m8_auto_prime_heat_seen = false;\n      m8_auto_prime_home_seen = false;\n      m8_auto_prime_done = false;\n    }\n  }\n'''
if old not in s:
    raise SystemExit("V7: M109 auto-prime tail not found")
s = s.replace(old, new, 1)
m109.write_text(s)

# --- SD Stop: deterministic direct lift + park, with no injected G27. ---
s = core.read_text()
inc_anchor = '#include "gcode/queue.h"\n'
externs = '''\n// Monster8 external-print handshake state (defined in G28.cpp).\nextern bool m8_auto_prime_home_seen;\nextern bool m8_auto_prime_heat_seen;\nextern bool m8_auto_prime_done;\n'''
if inc_anchor not in s:
    raise SystemExit("V7: MarlinCore queue include anchor missing")
if 'extern bool m8_auto_prime_heat_seen;' not in s:
    s = s.replace(inc_anchor, inc_anchor + externs, 1)

old_abort_queue = '''    queue.clear();\n    quickstop_stepper();\n'''
new_abort_queue = '''    // Clear every command source before synchronizing the stopped position.\n    // This prevents a prior injected park command from surviving into the next\n    // print and moving XY immediately after Z homing.\n    queue.inject_P(nullptr);\n    queue.inject("");\n    queue.clear();\n    quickstop_stepper();\n'''
# This sequence is unique inside abortSDPrinting in stock MarlinCore.cpp.
abort_start = s.find('inline void abortSDPrinting()')
abort_end = s.find('inline void finishSDPrinting()', abort_start)
if abort_start < 0 or abort_end < 0:
    raise SystemExit("V7: abortSDPrinting block not found")
segment = s[abort_start:abort_end]
if old_abort_queue not in segment:
    raise SystemExit("V7: abort queue/quickstop sequence not found")
segment = segment.replace(old_abort_queue, new_abort_queue, 1)

old_event = '''    #ifdef EVENT_GCODE_SD_ABORT\n      queue.inject(F(EVENT_GCODE_SD_ABORT));\n    #endif\n'''
new_event = '''    // A stopped print must not leave the external print handshake armed.\n    m8_auto_prime_home_seen = false;\n    m8_auto_prime_heat_seen = false;\n    m8_auto_prime_done = false;\n\n    // Do not queue G27 here. Stop is already executing in Marlin's main-loop\n    // context, so lift and park directly and synchronously. This guarantees\n    // physical Z motion completes before any XY park motion starts.\n    if (axis_is_trusted(Z_AXIS)) {\n      TERN_(HAS_LEVELING, set_bed_leveling_enabled(false));\n      const float m8_abort_safe_z = _MIN(float(Z_MAX_POS), _MAX(10.0f, current_position.z + 10.0f));\n      do_blocking_move_to_z(m8_abort_safe_z, 10.0f);\n      do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);\n      ui.set_status(F("Print stopped - parked"), 0);\n    }\n    else {\n      // With an untrusted Z axis, XY motion is deliberately forbidden.\n      ui.set_status(F("Print stopped - Z not trusted"), 0);\n    }\n'''
if old_event not in segment:
    raise SystemExit("V7: EVENT_GCODE_SD_ABORT injection not found")
segment = segment.replace(old_event, new_event, 1)
s = s[:abort_start] + segment + s[abort_end:]
core.write_text(s)

# ---------------------------------------------------------------------------
# Regression guards: preserve all proven bed / wiper / manual XY-zero behavior.
# ---------------------------------------------------------------------------
g28_text = g28.read_text()
m109_text = m109.read_text()
core_text = core.read_text()
bed_text = bed.read_text()
menu_text = menu.read_text()

for required in [
    'float m8_wiper_z = 3.50f;',
    'constexpr float XL = -35.0f, XR = -25.0f;',
    'constexpr float YF = -40.0f, YB = -20.0f;',
    'm8_auto_prime_heat_seen = false;',
    'do_blocking_move_to_z(10.0f, 10.0f);',
    'do_blocking_move_to_xy(10.0f, 10.0f, 40.0f);',
    'PSTR("G90\\nM83\\nG1 Z0.40 F600\\nG92 E0\\nG1 X%i E%i F600")',
]:
    if required not in g28_text:
        raise SystemExit(f"V7 G28 regression guard missing: {required}")

if 'G1 Z0.40 F600\\nG1 X10 Y10 F2400' in g28_text:
    raise SystemExit("V7: unsafe low-Z prime travel still present")

for required in [
    'const bool m8_heat_wait_ok = thermalManager.wait_for_hotend',
    'if (m8_heat_wait_ok && target_extruder == 0',
]:
    if required not in m109_text:
        raise SystemExit(f"V7 M109 guard missing: {required}")

for required in [
    'queue.inject_P(nullptr);',
    'queue.inject("");',
    'm8_auto_prime_home_seen = false;',
    'do_blocking_move_to_z(m8_abort_safe_z, 10.0f);',
    'do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);',
    'Print stopped - parked',
]:
    if required not in core_text:
        raise SystemExit(f"V7 abort guard missing: {required}")

# Abort must not enqueue a later G27 that can survive into a restart.
abort_segment = core_text[core_text.find('inline void abortSDPrinting()'):core_text.find('inline void finishSDPrinting()')]
if 'queue.inject(F(EVENT_GCODE_SD_ABORT))' in abort_segment:
    raise SystemExit("V7: queued SD-abort park still present")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"V7 bed regression guard failed: {required}")

for required in [
    'F("Wiper Enabled")',
    'F("Pattern Cycles")',
    'F("Test Hot Wipe")',
]:
    if required not in menu_text:
        raise SystemExit(f"V7 wiper menu regression failed: {required}")

print("Monster8 V7: safe stop/restart, fresh prime handshake, Z10 before all startup XY travel")
