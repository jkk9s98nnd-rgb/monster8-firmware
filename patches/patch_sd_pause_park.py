from pathlib import Path

root = Path("MarlinSource/Marlin")
conf = root / "Configuration.h"
adv = root / "Configuration_adv.h"
menu = root / "src/lcd/menu/menu_main.cpp"
m25 = root / "src/gcode/sd/M24_M25.cpp"
m1001 = root / "src/gcode/sd/M1001.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Standard Marlin nozzle parking, customized for the Monster8 work origin.
# X/Y are manually referenced, so X0/Y0 is the user's established work zero.
# Park always raises Z first, then moves XY at the same conservative 40mm/s
# used for the first Orca prints.
# ---------------------------------------------------------------------------
replace_once(conf, '//#define NOZZLE_PARK_FEATURE\n', '#define NOZZLE_PARK_FEATURE\n', "enable nozzle park")
replace_once(
    conf,
    '  #define NOZZLE_PARK_POINT { (X_MIN_POS + 10), (Y_MAX_POS - 10), 20 }\n',
    '  #define NOZZLE_PARK_POINT { 0, 0, 10 }\n',
    "park at work XY zero",
)
replace_once(conf, '  #define NOZZLE_PARK_Z_RAISE_MIN   2   // (mm) Always raise Z by at least this distance\n',
             '  #define NOZZLE_PARK_Z_RAISE_MIN  10   // (mm) Monster8: lift clear before XY park\n',
             "park Z raise")
replace_once(conf, '  #define NOZZLE_PARK_XY_FEEDRATE 100   // (mm/s) X and Y axes feedrate (also used for delta Z axis)\n',
             '  #define NOZZLE_PARK_XY_FEEDRATE  40   // (mm/s) Monster8 conservative XY park speed\n',
             "park XY feedrate")
replace_once(conf, '  #define NOZZLE_PARK_Z_FEEDRATE    5   // (mm/s) Z axis feedrate (not used for delta printers)\n',
             '  #define NOZZLE_PARK_Z_FEEDRATE   10   // (mm/s) Monster8 safe Z lift speed\n',
             "park Z feedrate")


# ---------------------------------------------------------------------------
# Pause / resume: use Marlin's proven M25 -> M125 park path. M125 stores the
# current print position, retracts, lifts, parks at X0/Y0, and M24 returns to
# the saved print position before continuing.
# ---------------------------------------------------------------------------
replace_once(adv, '//#define ADVANCED_PAUSE_FEATURE\n', '#define ADVANCED_PAUSE_FEATURE\n', "enable advanced pause")
replace_once(
    adv,
    '  //#define PARK_HEAD_ON_PAUSE                    // Park the nozzle during pause and filament change.\n',
    '  #define PARK_HEAD_ON_PAUSE                     // Monster8: M25 lifts and parks at X0/Y0; M24 returns\n',
    "enable park head on pause",
)


# ---------------------------------------------------------------------------
# STOP and normal SD completion use G27. With the park settings above G27:
#   1) raises Z by at least 10mm (capped at Z_MAX_POS), then
#   2) moves to the established native X0/Y0 at 40mm/s.
# Do not release steppers at normal completion so the manually established XY
# reference remains physically valid after the print.
# IMPORTANT: Marlin 2.1.2.8 defaults EVENT_GCODE_SD_ABORT to G28XY. That is
# unsafe on this machine because X/Y have no limit switches, so override it.
# ---------------------------------------------------------------------------
replace_once(
    adv,
    '  #define SD_FINISHED_STEPPERRELEASE true   // Disable steppers when SD Print is finished\n',
    '  #define SD_FINISHED_STEPPERRELEASE false  // Monster8: keep XY reference after parking\n',
    "keep steppers after SD completion",
)
replace_once(
    adv,
    '  #define SD_FINISHED_RELEASECOMMAND "M84"  // Use "M84XYE" to keep Z enabled so your bed stays in place\n',
    '  #define SD_FINISHED_RELEASECOMMAND "G27"  // Monster8: lift Z and park at X0/Y0 on completion\n',
    "park after SD completion",
)
replace_once(
    adv,
    '  #define EVENT_GCODE_SD_ABORT "G28XY"      // G-code to run on SD Abort Print (e.g., "G28XY" or "G27")\n',
    '  #define EVENT_GCODE_SD_ABORT "G27"        // Monster8: never home XY; lift and park on Stop Print\n',
    "safe SD abort park",
)


# ---------------------------------------------------------------------------
# Regression guards. Refuse to build if any of the proven Monster8 coordinate
# or mesh behavior disappears while adding print controls.
# ---------------------------------------------------------------------------
conf_text = conf.read_text()
adv_text = adv.read_text()
menu_text = menu.read_text()
m25_text = m25.read_text()
m1001_text = m1001.read_text()
bed_text = bed.read_text()

for required in [
    '#define NOZZLE_PARK_FEATURE',
    '#define NOZZLE_PARK_POINT { 0, 0, 10 }',
    '#define NOZZLE_PARK_Z_RAISE_MIN  10',
    '#define NOZZLE_PARK_XY_FEEDRATE  40',
    '#define NOZZLE_PARK_Z_FEEDRATE   10',
]:
    if required not in conf_text:
        raise SystemExit(f"Pause/park regression guard failed: {required}")

for required in [
    '#define ADVANCED_PAUSE_FEATURE',
    '#define PARK_HEAD_ON_PAUSE',
    '#define SD_FINISHED_STEPPERRELEASE false',
    '#define SD_FINISHED_RELEASECOMMAND "G27"',
    '#define EVENT_GCODE_SD_ABORT "G27"',
]:
    if required not in adv_text:
        raise SystemExit(f"Pause/park config guard failed: {required}")

if 'EVENT_GCODE_SD_ABORT "G28XY"' in adv_text:
    raise SystemExit("Unsafe G28XY SD abort command still present")

for required in [
    'ACTION_ITEM(MSG_PAUSE_PRINT, ui.pause_print);',
    'ui.abort_print',
]:
    if required not in menu_text:
        raise SystemExit(f"LCD print-control guard failed: {required}")

for required in [
    '#if ENABLED(PARK_HEAD_ON_PAUSE)',
    'M125();',
    'resume_print();',
]:
    if required not in m25_text:
        raise SystemExit(f"Marlin pause/resume guard failed: {required}")

if 'process_subcommands_now(F(SD_FINISHED_RELEASECOMMAND));' not in m1001_text:
    raise SystemExit("SD completion command hook missing")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Bed/XY-zero regression guard failed: {required}")

print("Enabled SD Pause/Resume park, safe Stop park, and completion park at X0/Y0 with 10mm Z lift")
