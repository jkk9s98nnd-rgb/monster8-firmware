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

// Monster8 external-print auto-prime. These values are intentionally RAM-only
// so no EEPROM layout changes can disturb the saved bed mesh or Z offset.
bool m8_auto_prime_lines = true;
int16_t m8_auto_prime_length = 60;   // mm per line
int16_t m8_auto_prime_count = 2;     // 1..3 lines
int16_t m8_auto_prime_e = 9;         // mm of filament per line
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

  // Clamp editable LCD values to the reserved safe prime strip.
  const int16_t plen = m8_auto_prime_length < 20 ? 20 : (m8_auto_prime_length > 100 ? 100 : m8_auto_prime_length);
  const int16_t pcount = m8_auto_prime_count < 1 ? 1 : (m8_auto_prime_count > 3 ? 3 : m8_auto_prime_count);
  const int16_t pe = m8_auto_prime_e < 1 ? 1 : (m8_auto_prime_e > 20 ? 20 : m8_auto_prime_e);
  const int16_t xend = 10 + plen;

  // Mark done before executing the subcommands so this cannot recurse.
  m8_auto_prime_done = true;
  ui.set_status(F("Auto Prime Lines"));

  // Build 1..3 alternating lines inside the proven 200x200 work area.
  // Y positions are 10, 12, 14. With the default two lines, keep models at
  // Y22 or higher; with three lines use Y24 or higher for ~10mm clearance.
  // Prime positioning travel is capped at 40mm/s (F2400).
  char cmd[256];
  int used = snprintf_P(
    cmd, sizeof(cmd),
    PSTR("G90\nM83\nG1 Z0.40 F600\nG1 X10 Y10 F2400\nG92 E0\nG1 X%i E%i F600"),
    int(xend), int(pe)
  );

  if (pcount >= 2 && used > 0 && used < int(sizeof(cmd)))
    used += snprintf_P(cmd + used, sizeof(cmd) - used, PSTR("\nG1 Y12 F1200\nG1 X10 E%i F600"), int(pe));

  if (pcount >= 3 && used > 0 && used < int(sizeof(cmd)))
    used += snprintf_P(cmd + used, sizeof(cmd) - used, PSTR("\nG1 Y14 F1200\nG1 X%i E%i F600"), int(xend), int(pe));

  if (used > 0 && used < int(sizeof(cmd)))
    snprintf_P(cmd + used, sizeof(cmd) - used, PSTR("\nG92 E0\nG1 Z2.00 F600"));

  gcode.process_subcommands_now(cmd);
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
# LCD auto-prime controls. Defaults target the current 0.8mm nozzle:
# 2 x 60mm lines with 9mm filament per line. Speed/Flow/Z Offset during an
# external print are already provided by Marlin's Tune menu; XY Set/Go Zero
# remain in Bed Level Setup so there is still only one master XY-zero control.
# ---------------------------------------------------------------------------
s = main.read_text()
if 'extern bool m8_auto_prime_lines;' not in s:
    anchor = 'extern bool m8_ignore_xy_home;\n'
    if anchor not in s:
        raise SystemExit("Ignore XY Home LCD declaration not found")
    s = s.replace(
        anchor,
        anchor
        + 'extern bool m8_auto_prime_lines;\n'
        + 'extern int16_t m8_auto_prime_length;\n'
        + 'extern int16_t m8_auto_prime_count;\n'
        + 'extern int16_t m8_auto_prime_e;\n',
        1,
    )

line = '  EDIT_ITEM_F(bool, F("Ignore XY Home"), &m8_ignore_xy_home);\n'
if line not in s:
    raise SystemExit("Ignore XY Home LCD item not found")
if 'F("Auto Prime Lines")' not in s:
    s = s.replace(
        line,
        line
        + '  EDIT_ITEM_F(bool, F("Auto Prime Lines"), &m8_auto_prime_lines);\n'
        + '  EDIT_ITEM_F(int3, F("Prime Length mm"), &m8_auto_prime_length, 20, 100);\n'
        + '  EDIT_ITEM_F(int3, F("Prime Lines"), &m8_auto_prime_count, 1, 3);\n'
        + '  EDIT_ITEM_F(int3, F("Prime E/Line mm"), &m8_auto_prime_e, 1, 20);\n',
        1,
    )
main.write_text(s)


# ---------------------------------------------------------------------------
# Regression guards: external auto-prime must not rewrite the working bed mesh
# or remove the single master XY-zero controls.
# ---------------------------------------------------------------------------
bed_text = bed.read_text()
for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500")',
    'ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Auto-prime refuses build: bed-level regression guard failed: {required}")

for required in [
    'int16_t m8_auto_prime_length = 60;',
    'int16_t m8_auto_prime_count = 2;',
    'int16_t m8_auto_prime_e = 9;',
    'G1 X10 Y10 F2400',
]:
    if required not in g28.read_text():
        raise SystemExit(f"Auto-prime control regression guard failed: {required}")

print("Added adjustable external Auto Prime controls: 1..3 lines, 20..100mm length, 1..20mm E/line; preserved mesh and XY zero")
