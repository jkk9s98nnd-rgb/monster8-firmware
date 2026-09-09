from pathlib import Path

root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
g29 = root / "src/gcode/bedlevel/abl/G29.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# V10: Do the post-mesh save / lift / X0 Y0 return directly inside G29.
#
# V8/V9 appended commands after G29 in the injected LCD command string. On this
# machine the mesh itself completes, but the commands queued after G29 are not
# reliably executed. Remove that dependency entirely. The LCD mesh runner arms
# a one-shot flag; successful G29 completion then synchronously saves, lifts,
# and moves to logical X0/Y0 before returning to the command queue.
# ---------------------------------------------------------------------------

# G29 needs direct EEPROM save access.
replace_once(
    g29,
    '#include "../../../module/probe.h"\n',
    '#include "../../../module/probe.h"\n#include "../../../module/settings.h"\n',
    "G29 settings include",
)

# Add a one-shot flag beside the existing Monster8 mesh diagnostics.
replace_once(
    g29,
    '''#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n#endif\n''',
    '''#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n  bool m8_lcd_mesh_finish_pending = false;\n#endif\n''',
    "G29 LCD mesh finish flag",
)

# Bed-level menu sees the same flag.
replace_once(
    bed,
    '''#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n#endif\n''',
    '''#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n  extern bool m8_lcd_mesh_finish_pending;\n#endif\n''',
    "Bed menu LCD mesh finish extern",
)

# V9's long post-G29 tail is no longer needed. G29 itself will do the work.
replace_once(
    bed,
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM420 S1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400")',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1")',
    "remove queued post-G29 tail",
)

# Arm the one-shot action immediately before injecting the LCD mesh command.
replace_once(
    bed,
    '''  queue.inject(cmd);\n}\n\nstatic void m8_show_last_mesh() {\n''',
    '''  m8_lcd_mesh_finish_pending = true;\n  queue.inject(cmd);\n}\n\nstatic void m8_show_last_mesh() {\n''',
    "arm direct G29 finish action",
)

# Execute the requested finish actions inside G29 after probing is fully done,
# the probe is stowed, and the mesh has been calculated/enabled. This is direct
# blocking motion, not queued G-code, so it cannot be skipped after G29.
replace_once(
    g29,
    '''  TERN_(HAS_MULTI_HOTEND, if (abl.tool_index != 0) tool_change(abl.tool_index));\n\n  report_current_position();\n\n  G29_RETURN(isnan(abl.measured_z), true);\n''',
    '''  TERN_(HAS_MULTI_HOTEND, if (abl.tool_index != 0) tool_change(abl.tool_index));\n\n  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    if (m8_lcd_mesh_finish_pending) {\n      m8_lcd_mesh_finish_pending = false;\n\n      if (!isnan(abl.measured_z) && leveling_is_valid()) {\n        // Make the new mesh active before saving. V9 also restores a valid\n        // saved bilinear mesh automatically after reboot / M501.\n        set_bed_leveling_enabled(true);\n        planner.synchronize();\n        (void)settings.save();\n\n        // Physically clear the bed, then return to Mark's logical X0/Y0.\n        // Use direct blocking motion so no later queue state can suppress it.\n        const float m8_return_z = _MIN(float(Z_MAX_POS), current_position.z + 10.0f);\n        do_blocking_move_to_z(m8_return_z, 10.0f);\n        do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);\n        planner.synchronize();\n\n        ui.set_status(F("MESH SAVED - X0 Y0"), 0);\n      }\n      else {\n        ui.set_status(F("MESH FAILED - NOT SAVED"), 0);\n      }\n    }\n  #endif\n\n  report_current_position();\n\n  G29_RETURN(isnan(abl.measured_z), true);\n''',
    "direct successful mesh save lift and XY0 return",
)


# ---------------------------------------------------------------------------
# Regression guards.
# ---------------------------------------------------------------------------
bed_text = bed.read_text()
g29_text = g29.read_text()

for required in [
    'extern bool m8_lcd_mesh_finish_pending;',
    'm8_lcd_mesh_finish_pending = true;',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1")',
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
]:
    if required not in bed_text:
        raise SystemExit(f"V10 bed regression guard missing: {required}")

# The old queued motion must be gone from the active final mesh command.
if 'G29 P%u L%i R%i F%i B%i E V1\\nM420 S1\\nM500\\nG91' in bed_text:
    raise SystemExit("V10: queued post-G29 finish tail still present")

for required in [
    '#include "../../../module/settings.h"',
    'bool m8_lcd_mesh_finish_pending = false;',
    'if (m8_lcd_mesh_finish_pending)',
    '(void)settings.save();',
    'do_blocking_move_to_z(m8_return_z, 10.0f);',
    'do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);',
    'MESH SAVED - X0 Y0',
]:
    if required not in g29_text:
        raise SystemExit(f"V10 G29 regression guard missing: {required}")

print("Monster8 V10: successful LCD mesh now directly saves, lifts 10mm, and blocks until X0 Y0 return is complete")
