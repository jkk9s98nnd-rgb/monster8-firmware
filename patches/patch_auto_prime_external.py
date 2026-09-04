from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
m109 = root / "src/gcode/temp/M104_M109.cpp"
main = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"


def find_function_end(text: str, signature: str) -> int:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f"opening brace not found: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
    raise SystemExit(f"closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# G28: track a plain slicer G28 and run the prime only after BOTH Z homing and
# an M109 hotend wait have completed. Bed leveling and the internal test cube
# use explicit G28 Z, so they never arm this external-print prime routine.
# ---------------------------------------------------------------------------
s = g28.read_text()

if '#include "../../module/temperature.h"\n' not in s:
    anchor = '#include "../../module/planner.h"\n'
    if anchor not in s:
        raise SystemExit("G28 planner include anchor not found")
    s = s.replace(anchor, anchor + '#include "../../module/temperature.h"\n', 1)

anchor = 'bool m8_ignore_xy_home = true;\n'
if anchor not in s:
    raise SystemExit("Orca XY-home guard must be applied before auto-prime")

helper = r'''

// Monster8 external-print auto-prime. This is intentionally RAM-only so no
// EEPROM layout changes can disturb the saved bed mesh or Z offset.
bool m8_auto_prime_lines = true;
bool m8_auto_prime_home_seen = false;
bool m8_auto_prime_heat_seen = false;
bool m8_auto_prime_done = false;

void m8_auto_prime_try() {
  if (!m8_auto_prime_lines || !m8_ignore_xy_home
      || !m8_auto_prime_home_seen || !m8_auto_prime_heat_seen
      || m8_auto_prime_done)
    return;

  // Never extrude unless the nozzle is actually hot enough.
  if (thermalManager.degHotend(0) < EXTRUDE_MINTEMP)
    return;

  // Mark done before executing the subcommands so this cannot recurse.
  m8_auto_prime_done = true;
  ui.set_status(F("Auto Prime Lines"));

  // Fixed reserved prime strip inside the proven 200x200 work area.
  // Two 30mm lines at Y10/Y12, intended for the current 0.8mm nozzle.
  // Keep sliced models at Y22 or higher for ~10mm clearance from the strip.
  gcode.process_subcommands_now(F(
    "G90\n"
    "M83\n"
    "G1 Z0.40 F600\n"
    "G1 X10 Y10 F3000\n"
    "G92 E0\n"
    "G1 X40 E4.50 F600\n"
    "G1 Y12 F1200\n"
    "G1 X10 E4.50 F600\n"
    "G92 E0\n"
    "G1 Z2.00 F600"
  ));
}
'''

if 'bool m8_auto_prime_lines = true;' not in s:
    s = s.replace(anchor, anchor + helper, 1)

sig = 'void GcodeSuite::G28() {'
start = s.find(sig)
if start < 0:
    raise SystemExit("G28 function not found")
insert_after = s.find('\n', s.find('if (DEBUGGING(LEVELING)) log_machine_info();', start)) + 1
if insert_after <= 0:
    raise SystemExit("G28 debug prologue not found")
plain_decl = '  const bool m8_plain_slicer_home = !parser.seen_axis();\n'
if plain_decl not in s[start:start+600]:
    s = s[:insert_after] + '\n' + plain_decl + s[insert_after:]

end = find_function_end(s, sig)
end_hook = r'''

  // A plain G28 is the slicer-print handshake on this machine. With Ignore XY
  // Home ON it has just homed Z only. Arm / run auto-prime after homing.
  if (m8_plain_slicer_home && m8_ignore_xy_home) {
    m8_auto_prime_home_seen = true;
    m8_auto_prime_done = false;
    m8_auto_prime_try();
  }
'''
if 'm8_auto_prime_home_seen = true;' not in s[start:end]:
    s = s[:end] + end_hook + s[end:]

g28.write_text(s)


# ---------------------------------------------------------------------------
# M109: signal that the hotend has reached print temperature. If G28 already
# happened, prime now. If M109 happened first, G28 will prime when it finishes.
# M104/M109 to a cold target resets the handshake for the next print.
# ---------------------------------------------------------------------------
s = m109.read_text()
externs = r'''

extern bool m8_auto_prime_home_seen;
extern bool m8_auto_prime_heat_seen;
extern bool m8_auto_prime_done;
void m8_auto_prime_try();
'''
inc_anchor = '#include "../../MarlinCore.h" // for startOrResumeJob, etc.\n'
if inc_anchor not in s:
    raise SystemExit("M109 MarlinCore include anchor not found")
if 'extern bool m8_auto_prime_heat_seen;' not in s:
    s = s.replace(inc_anchor, inc_anchor + externs, 1)

old_tail = '''  if (isM109 && got_temp)\n    (void)thermalManager.wait_for_hotend(target_extruder, no_wait_for_cooling);\n'''
new_tail = '''  if (isM109 && got_temp) {\n    (void)thermalManager.wait_for_hotend(target_extruder, no_wait_for_cooling);\n    if (target_extruder == 0 && temp >= EXTRUDE_MINTEMP) {\n      m8_auto_prime_heat_seen = true;\n      m8_auto_prime_try();\n    }\n    else if (temp < EXTRUDE_MINTEMP) {\n      m8_auto_prime_heat_seen = false;\n      m8_auto_prime_home_seen = false;\n      m8_auto_prime_done = false;\n    }\n  }\n  else if (got_temp && target_extruder == 0 && temp < EXTRUDE_MINTEMP) {\n    // Typical M104 S0 end-code resets the auto-prime handshake.\n    m8_auto_prime_heat_seen = false;\n    m8_auto_prime_home_seen = false;\n    m8_auto_prime_done = false;\n  }\n'''
if old_tail not in s:
    raise SystemExit("M109 wait tail not found")
s = s.replace(old_tail, new_tail, 1)
m109.write_text(s)


# ---------------------------------------------------------------------------
# LCD toggle. Default is ON. Turning it OFF restores ordinary slicer behavior.
# ---------------------------------------------------------------------------
s = main.read_text()
if 'extern bool m8_auto_prime_lines;' not in s:
    anchor = 'extern bool m8_ignore_xy_home;\n'
    if anchor not in s:
        raise SystemExit("Ignore XY Home LCD declaration not found")
    s = s.replace(anchor, anchor + 'extern bool m8_auto_prime_lines;\n', 1)

line = '  EDIT_ITEM_F(bool, F("Ignore XY Home"), &m8_ignore_xy_home);\n'
if line not in s:
    raise SystemExit("Ignore XY Home LCD item not found")
if 'F("Auto Prime Lines")' not in s:
    s = s.replace(line, line + '  EDIT_ITEM_F(bool, F("Auto Prime Lines"), &m8_auto_prime_lines);\n', 1)
main.write_text(s)


# ---------------------------------------------------------------------------
# Regression guard: external auto-prime must not rewrite the working bed mesh.
# ---------------------------------------------------------------------------
bed_text = bed.read_text()
for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500")',
    'ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);',
]:
    if required not in bed_text:
        raise SystemExit(f"Auto-prime refuses build: bed-level regression guard failed: {required}")

print("Added selectable external Auto Prime Lines at X10..40, Y10/Y12 without changing bed leveling")
