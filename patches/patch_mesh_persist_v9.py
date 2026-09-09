from pathlib import Path

root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
settings = root / "src/module/settings.cpp"
conf = root / "Configuration.h"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1) The V8 post-mesh command became longer than the original 80-byte runtime
#    command buffer. That could truncate the tail, which explains why the mesh
#    completed but the Z lift / X0 Y0 return didn't run (and could also cut off
#    M500 depending on formatted coordinate widths). Make the buffer comfortably
#    large and explicitly enable the fresh mesh before saving it.
# ---------------------------------------------------------------------------
replace_once(
    bed,
    "  char cmd[80];\n",
    "  char cmd[160];\n",
    "expand mesh command buffer",
)

replace_once(
    bed,
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400")',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM420 S1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400")',
    "enable save and return after mesh",
)


# ---------------------------------------------------------------------------
# 2) Bilinear Marlin saves the mesh values in EEPROM, but unlike UBL it stores
#    the active-state flag as false. On the Monster8 we always want a valid saved
#    bilinear mesh to come back active after a power cycle / M501.
#
#    Settings load happens before normal motion, so set the planner flag directly
#    rather than applying a coordinate correction to an un-homed position.
# ---------------------------------------------------------------------------
replace_once(
    settings,
    '''      const bool success = (err == ERR_EEPROM_NOERR);\n      TERN_(EXTENSIBLE_UI, ExtUI::onSettingsLoaded(success));\n      return success;\n''',
    '''      const bool success = (err == ERR_EEPROM_NOERR);\n      #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n        if (success && leveling_is_valid()) {\n          planner.leveling_active = true;\n          TERN_(HAS_STATUS_MESSAGE, ui.set_status(F("Saved mesh loaded"), 0));\n        }\n      #endif\n      TERN_(EXTENSIBLE_UI, ExtUI::onSettingsLoaded(success));\n      return success;\n''',
    "auto-enable valid saved bilinear mesh on EEPROM load",
)


# ---------------------------------------------------------------------------
# 3) Preserve that active state through G28. This matters because the Monster8
#    homes Z at the start of prints and bed-level operations, while X/Y remain
#    manually referenced.
# ---------------------------------------------------------------------------
replace_once(
    conf,
    "//#define RESTORE_LEVELING_AFTER_G28\n",
    "#define RESTORE_LEVELING_AFTER_G28\n",
    "restore leveling after G28",
)


# ---------------------------------------------------------------------------
# Regression guards.
# ---------------------------------------------------------------------------
bed_text = bed.read_text()
settings_text = settings.read_text()
conf_text = conf.read_text()

for required in [
    "char cmd[160];",
    'G29 P%u L%i R%i F%i B%i E V1\\nM420 S1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'const int16_t map_left  = 10,',
    'map_front = 10,',
]:
    if required not in bed_text:
        raise SystemExit(f"V9 bed regression guard missing: {required}")

for required in [
    'if (success && leveling_is_valid())',
    'planner.leveling_active = true;',
    'Saved mesh loaded',
]:
    if required not in settings_text:
        raise SystemExit(f"V9 EEPROM mesh guard missing: {required}")

if '#define RESTORE_LEVELING_AFTER_G28' not in conf_text:
    raise SystemExit("V9 restore-leveling guard missing")

print("Monster8 V9: full post-mesh lift/XY0 command, M500 persistence, saved bilinear mesh auto-active after reboot")
