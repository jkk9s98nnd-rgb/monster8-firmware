from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
main = root / "src/lcd/menu/menu_main.cpp"

# ---------------------------------------------------------------------------
# G28 guard
# ---------------------------------------------------------------------------
s = g28.read_text()

anchor = '#include "../../core/debug_out.h"\n'
if anchor not in s:
    raise SystemExit("G28 debug include anchor not found")
if "bool m8_ignore_xy_home" not in s:
    s = s.replace(
        anchor,
        anchor + '\n// Monster8 / Orca compatibility: default ON because this machine has no X/Y\n'
                 '// homing switches. LCD can toggle this at runtime.\n'
                 'bool m8_ignore_xy_home = true;\n',
        1
    )

start_anchor = '''void GcodeSuite::G28() {
  DEBUG_SECTION(log_G28, "G28", DEBUGGING(LEVELING));
  if (DEBUGGING(LEVELING)) log_machine_info();
'''
if start_anchor not in s:
    raise SystemExit("G28 function start anchor not found")
if "XY homing ignored by Orca guard" not in s:
    s = s.replace(
        start_anchor,
        start_anchor + '''

  // With the guard enabled, explicit X/Y-only homing commands are ignored.
  // Commands that include Z are allowed to continue, but X/Y are filtered
  // below. A plain G28 is interpreted as Z-only homing.
  if (m8_ignore_xy_home && parser.seen_axis() && !parser.seen_test('Z')) {
    ui.set_status(F("XY Home Ignored"), 0);
    SERIAL_ECHO_MSG("XY homing ignored by Orca guard");
    return;
  }
''',
        1
    )

old = """    const bool homeZ = TERN0(HAS_Z_AXIS, parser.seen_test('Z')),
               NUM_AXIS_LIST(              // Other axes should be homed before Z safe-homing
                 needX = _UNSAFE(X), needY = _UNSAFE(Y), needZ = false, // UNUSED
                 needI = _UNSAFE(I), needJ = _UNSAFE(J), needK = _UNSAFE(K),
                 needU = _UNSAFE(U), needV = _UNSAFE(V), needW = _UNSAFE(W)
               ),
               NUM_AXIS_LIST(              // Home each axis if needed or flagged
                 homeX = needX || parser.seen_test('X'),
                 homeY = needY || parser.seen_test('Y'),
                 homeZZ = homeZ,
                 homeI = needI || parser.seen_test(AXIS4_NAME), homeJ = needJ || parser.seen_test(AXIS5_NAME),
                 homeK = needK || parser.seen_test(AXIS6_NAME), homeU = needU || parser.seen_test(AXIS7_NAME),
                 homeV = needV || parser.seen_test(AXIS8_NAME), homeW = needW || parser.seen_test(AXIS9_NAME)
               ),
               home_all = NUM_AXIS_GANG(   // Home-all if all or none are flagged
                    homeX == homeX, && homeY == homeX, && homeZ == homeX,
                 && homeI == homeX, && homeJ == homeX, && homeK == homeX,
                 && homeU == homeX, && homeV == homeX, && homeW == homeX
               ),
"""
new = """    const bool homeZ = TERN0(HAS_Z_AXIS, parser.seen_test('Z') || (m8_ignore_xy_home && !parser.seen_axis())),
               NUM_AXIS_LIST(              // Other axes should be homed before Z safe-homing
                 needX = _UNSAFE(X), needY = _UNSAFE(Y), needZ = false, // UNUSED
                 needI = _UNSAFE(I), needJ = _UNSAFE(J), needK = _UNSAFE(K),
                 needU = _UNSAFE(U), needV = _UNSAFE(V), needW = _UNSAFE(W)
               ),
               NUM_AXIS_LIST(              // Home each axis if needed or flagged
                 homeX = needX || (!m8_ignore_xy_home && parser.seen_test('X')),
                 homeY = needY || (!m8_ignore_xy_home && parser.seen_test('Y')),
                 homeZZ = homeZ,
                 homeI = needI || parser.seen_test(AXIS4_NAME), homeJ = needJ || parser.seen_test(AXIS5_NAME),
                 homeK = needK || parser.seen_test(AXIS6_NAME), homeU = needU || parser.seen_test(AXIS7_NAME),
                 homeV = needV || parser.seen_test(AXIS8_NAME), homeW = needW || parser.seen_test(AXIS9_NAME)
               ),
               home_all = !m8_ignore_xy_home && NUM_AXIS_GANG(   // Normal home-all only when guard is OFF
                    homeX == homeX, && homeY == homeX, && homeZ == homeX,
                 && homeI == homeX, && homeJ == homeX, && homeK == homeX,
                 && homeU == homeX, && homeV == homeX, && homeW == homeX
               ),
"""
if old not in s:
    raise SystemExit("G28 axis-selection block not found")
s = s.replace(old, new, 1)
g28.write_text(s)

# ---------------------------------------------------------------------------
# LCD checkbox on the main menu
# ---------------------------------------------------------------------------
s = main.read_text()

fn_anchor = "void menu_main() {\n"
if fn_anchor not in s:
    raise SystemExit("menu_main function not found")
if "extern bool m8_ignore_xy_home;" not in s:
    s = s.replace(fn_anchor, "extern bool m8_ignore_xy_home;\n\n" + fn_anchor, 1)

menu_anchor = """  START_MENU();
  BACK_ITEM(MSG_INFO_SCREEN);
"""
if menu_anchor not in s:
    raise SystemExit("main menu start anchor not found")
if 'F("Ignore XY Home")' not in s:
    s = s.replace(
        menu_anchor,
        menu_anchor + '  EDIT_ITEM_F(bool, F("Ignore XY Home"), &m8_ignore_xy_home);\n',
        1
    )

main.write_text(s)

# Regression guard: this feature is not allowed to build unless the bed-level
# path is still the exact native-zero + 10mm-inset implementation proven on
# the printer.
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
bed_text = bed.read_text()
for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500")',
    'ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);',
]:
    if required not in bed_text:
        raise SystemExit(f"Orca guard refuses to build because bed-level regression guard failed: {required}")

print("Added selectable Ignore XY Home guard; plain G28 becomes Z-only while guard is ON")
