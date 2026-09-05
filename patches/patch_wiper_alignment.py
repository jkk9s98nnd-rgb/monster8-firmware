from pathlib import Path

root = Path("MarlinSource/Marlin")
main = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
conf = root / "Configuration.h"
adv = root / "Configuration_adv.h"

s = main.read_text()

# ---------------------------------------------------------------------------
# Monster8 nozzle-wiper alignment helper.
# The planned AD5X rubber wiper is centered at native X-30 / Y-30, rotated so
# its 8.4mm dimension runs along X and its 18.8mm dimension runs along Y.
# This first-stage wizard DOES NOT touch the rubber. It parks/lifts safely,
# disables mesh compensation before leaving the mapped bed, moves to the
# intended wiper center, then lowers only to Z10.0. With a 4.8mm-tall wiper
# this leaves ~5.2mm clearance while Mark physically centers and sticks it down.
# Automatic contact wiping stays out of this build until the physical location
# and contact Z have been verified on the machine.
# ---------------------------------------------------------------------------
helper_anchor = "void menu_configuration();\n"
helper = r'''

static void m8_wiper_align_center() {
  // G27 is provided by the proven Monster8 pause/park build: it raises Z by
  // at least 10mm and parks at the established native X0/Y0 without homing XY.
  // Turn leveling off before leaving the 200x200 mapped area, then move to the
  // wiper center and lower only to a clearly safe alignment height.
  queue.inject(F("M420 S0\nG27\nG90\nG1 X-30 Y-30 F2400\nG1 Z10.0 F600\nM117 Center wiper under nozzle"));
  ui.return_to_status();
}

static void m8_wiper_return_zero() {
  // Lift/park with the same safe G27 routine. Leave leveling off; the Orca
  // start sequence explicitly restores the saved mesh with M420 S1.
  queue.inject(F("M420 S0\nG27\nM117 Wiper setup done"));
  ui.return_to_status();
}

static void m8_wiper_setup_menu() {
  START_MENU();
  BACK_ITEM(MSG_MAIN_MENU);
  ACTION_ITEM_F(F("Align Wiper Center"), m8_wiper_align_center);
  ACTION_ITEM_F(F("Return XY Zero"), m8_wiper_return_zero);
  STATIC_ITEM_F(F("Center X -30 Y -30"));
  STATIC_ITEM_F(F("Wiper 8.4 X / 18.8 Y"));
  STATIC_ITEM_F(F("Align height Z10"));
  END_MENU();
}
'''

if 'static void m8_wiper_align_center()' not in s:
    if helper_anchor not in s:
        raise SystemExit("Wiper wizard: menu helper anchor not found")
    s = s.replace(helper_anchor, helper_anchor + helper, 1)

# Show Wiper Setup only while idle. Do not allow alignment motion during a print.
idle_anchor = """    SUBMENU(MSG_MOTION, menu_motion);\n"""
if 'SUBMENU_F(F("Wiper Setup"), m8_wiper_setup_menu);' not in s:
    if idle_anchor not in s:
        raise SystemExit("Wiper wizard: idle Motion menu anchor not found")
    s = s.replace(
        idle_anchor,
        '    SUBMENU_F(F("Wiper Setup"), m8_wiper_setup_menu);\n' + idle_anchor,
        1,
    )

main.write_text(s)

# ---------------------------------------------------------------------------
# Regression guards. Refuse to build unless all the already-proven Monster8
# safety behavior is still present: native XY zero, 10mm mesh inset, G27 park,
# no G28XY abort, and the alignment target / safe-height commands.
# ---------------------------------------------------------------------------
main_text = main.read_text()
bed_text = bed.read_text()
conf_text = conf.read_text()
adv_text = adv.read_text()

for required in [
    'ACTION_ITEM_F(F("Align Wiper Center"), m8_wiper_align_center);',
    'G1 X-30 Y-30 F2400',
    'G1 Z10.0 F600',
    'M420 S0\\nG27',
    'SUBMENU_F(F("Wiper Setup"), m8_wiper_setup_menu);',
]:
    if required not in main_text:
        raise SystemExit(f"Wiper alignment regression guard failed: {required}")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper wizard refuses build: bed/XY-zero regression: {required}")

for required in [
    '#define NOZZLE_PARK_FEATURE',
    '#define NOZZLE_PARK_POINT { 0, 0, 10 }',
]:
    if required not in conf_text:
        raise SystemExit(f"Wiper wizard refuses build: park config missing: {required}")

for required in [
    '#define SD_FINISHED_STEPPERRELEASE false',
    '#define EVENT_GCODE_SD_ABORT "G27"',
]:
    if required not in adv_text:
        raise SystemExit(f"Wiper wizard refuses build: safe SD behavior missing: {required}")

if 'EVENT_GCODE_SD_ABORT "G28XY"' in adv_text:
    raise SystemExit("Wiper wizard refuses build: unsafe G28XY abort returned")

print("Added idle-only Wiper Setup alignment wizard at X-30 Y-30, safe Z10 alignment height")
