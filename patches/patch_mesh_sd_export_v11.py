from pathlib import Path

root = Path("MarlinSource/Marlin")
g29 = root / "src/gcode/bedlevel/abl/G29.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# V11: Export every successful LCD mesh to a unique CSV on the SD card.
#
# The file format deliberately stores coordinates in micrometers as integers.
# This avoids embedded printf floating-point dependencies and preserves the
# measured values exactly enough for the Windows mesh viewer. The viewer
# converts these values back to millimeters.
#
# Files are named MESH0001.CSV ... MESH9999.CSV and are never overwritten.
# EEPROM save remains the primary persistence mechanism; SD export is optional
# and a missing/full/unmounted card must never make bed leveling fail.
# ---------------------------------------------------------------------------

replace_once(
    g29,
    '#include "../../../module/settings.h"\n',
    '#include "../../../module/settings.h"\n#if HAS_MEDIA\n  #include "../../../sd/cardreader.h"\n#endif\n',
    "G29 SD card include",
)

old = '''        set_bed_leveling_enabled(true);\n        planner.synchronize();\n        (void)settings.save();\n\n        const float m8_return_z = _MIN(float(Z_MAX_POS), current_position.z + 10.0f);\n'''

new = '''        set_bed_leveling_enabled(true);\n        planner.synchronize();\n        (void)settings.save();\n\n        // Optional SD export for the Monster8 PC mesh viewer. EEPROM save\n        // above remains authoritative, so any SD problem is non-fatal.\n        #if HAS_MEDIA && ENABLED(AUTO_BED_LEVELING_BILINEAR)\n          bool m8_csv_saved = false;\n          char m8_csv_name[13] = { 0 }; // 8.3 name + NUL: MESH0001.CSV\n\n          if (!card.isMounted()) card.mount();\n          if (card.isMounted()) {\n            for (uint16_t n = 1; n <= 9999; ++n) {\n              snprintf_P(m8_csv_name, sizeof(m8_csv_name), PSTR("MESH%04u.CSV"), unsigned(n));\n              if (!card.fileExists(m8_csv_name)) break;\n              if (n == 9999) m8_csv_name[0] = '\\0';\n            }\n\n            if (m8_csv_name[0]) {\n              card.openFileWrite(m8_csv_name);\n              if (card.isFileOpen()) {\n                char line[96];\n                auto m8_write = [&](const char * const text) {\n                  card.write((void*)text, uint16_t(strlen(text)));\n                };\n                auto m8_write_pair = [&](PGM_P key, const int32_t value) {\n                  const int len = snprintf_P(line, sizeof(line), PSTR("%S,%ld\\r\\n"), key, long(value));\n                  if (len > 0) card.write(line, uint16_t(len));\n                };\n\n                m8_write("MONSTER8_MESH,1\\r\\n");\n                m8_write_pair(PSTR("GRID_POINTS"), int32_t(abl.grid_points.x));\n                m8_write_pair(PSTR("MAP_LEFT_UM"),  int32_t(lroundf(abl.probe_position_lf.x * 1000.0f)));\n                m8_write_pair(PSTR("MAP_RIGHT_UM"), int32_t(lroundf(abl.probe_position_rb.x * 1000.0f)));\n                m8_write_pair(PSTR("MAP_FRONT_UM"), int32_t(lroundf(abl.probe_position_lf.y * 1000.0f)));\n                m8_write_pair(PSTR("MAP_BACK_UM"),  int32_t(lroundf(abl.probe_position_rb.y * 1000.0f)));\n                m8_write_pair(PSTR("INTERNAL_GRID_POINTS"), int32_t(GRID_MAX_POINTS_X));\n                m8_write("X_UM,Y_UM,Z_UM\\r\\n");\n\n                for (uint8_t iy = 0; iy < abl.grid_points.y; ++iy) {\n                  const float fy = abl.grid_points.y > 1 ? float(iy) / float(abl.grid_points.y - 1) : 0.0f;\n                  const float y = abl.probe_position_lf.y + (abl.probe_position_rb.y - abl.probe_position_lf.y) * fy;\n                  for (uint8_t ix = 0; ix < abl.grid_points.x; ++ix) {\n                    const float fx = abl.grid_points.x > 1 ? float(ix) / float(abl.grid_points.x - 1) : 0.0f;\n                    const float x = abl.probe_position_lf.x + (abl.probe_position_rb.x - abl.probe_position_lf.x) * fx;\n                    const int len = snprintf_P(\n                      line, sizeof(line), PSTR("%ld,%ld,%ld\\r\\n"),\n                      long(lroundf(x * 1000.0f)),\n                      long(lroundf(y * 1000.0f)),\n                      long(lroundf(abl.sampled_z_values[ix][iy] * 1000.0f))\n                    );\n                    if (len > 0) card.write(line, uint16_t(len));\n                  }\n                }\n\n                card.closefile();\n                m8_csv_saved = true;\n              }\n            }\n          }\n        #endif\n\n        const float m8_return_z = _MIN(float(Z_MAX_POS), current_position.z + 10.0f);\n'''
replace_once(g29, old, new, "V11 SD mesh export body")

# Replace V10's final status with a status that confirms whether a CSV was made.
replace_once(
    g29,
    '        ui.set_status(F("MESH SAVED - X0 Y0"), 0);\n',
    '''        #if HAS_MEDIA && ENABLED(AUTO_BED_LEVELING_BILINEAR)\n          if (m8_csv_saved)\n            ui.status_printf(0, F("%s SAVED"), m8_csv_name);\n          else\n            ui.set_status(F("MESH SAVED - EEPROM"), 0);\n        #else\n          ui.set_status(F("MESH SAVED - X0 Y0"), 0);\n        #endif\n''',
    "V11 mesh export status",
)

text = g29.read_text()
for required in [
    '#include "../../../sd/cardreader.h"',
    'MESH%04u.CSV',
    'MONSTER8_MESH,1',
    'GRID_POINTS',
    'X_UM,Y_UM,Z_UM',
    'abl.sampled_z_values[ix][iy]',
    'card.closefile();',
    'MESH SAVED - EEPROM',
    '(void)settings.save();',
    'do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);',
]:
    if required not in text:
        raise SystemExit(f"V11 regression guard missing: {required}")

print("Monster8 V11: successful LCD mesh saves EEPROM + unique MESH####.CSV to SD, then returns X0 Y0")
