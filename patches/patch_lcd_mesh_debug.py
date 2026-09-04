from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
probe = root / "src/module/probe.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
g29 = root / "src/gcode/bedlevel/abl/G29.cpp"

# ---------------------------------------------------------------------------
# Runtime state shared by the probe, G29, and the LCD Bed Level Setup menu.
# ---------------------------------------------------------------------------
replace_once(
    probe,
    """Probe probe;\n\nxyz_pos_t Probe::offset; // Initialized by settings.load\n""",
    """Probe probe;\n\n#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  int16_t m8_mesh_safe_z = 10;      // LCD adjustable: 6..20mm\n  uint8_t m8_probe_fail_reason = 0; // 1=pretrigger, 2=no trigger, 3=early trigger\n  uint8_t m8_mesh_last_point = 0;\n  int16_t m8_mesh_last_x = 0, m8_mesh_last_y = 0;\n#endif\n\nxyz_pos_t Probe::offset; // Initialized by settings.load\n""",
    "MicroProbe LCD diagnostic globals",
)

# ---------------------------------------------------------------------------
# Correct the old backport behavior: during G29 the probe MUST raise Z before
# deploy/stow. The old shortcut left deploy/stow motionless, which allowed the
# extended MicroProbe pin to contact the bed between mesh points.
# ---------------------------------------------------------------------------
replace_once(
    probe,
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    constexpr bool z_raise_wanted = false;\n  #elif ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    constexpr bool z_raise_wanted = true;\n  #elif ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n""",
    "restore MicroProbe deploy/stow Z raise",
)

replace_once(
    probe,
    """  if (z_raise_wanted)\n    do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    if (z_raise_wanted) do_z_raise(float(m8_mesh_safe_z));\n  #else\n    if (z_raise_wanted)\n      do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));\n  #endif\n""",
    "runtime MicroProbe deploy/stow clearance",
)

# If G29 is ever run without E, use the same runtime clearance for the normal
# between-point raise path too.
replace_once(
    probe,
    """    if (raise_after == PROBE_PT_RAISE)\n      do_blocking_move_to_z(current_position.z + Z_CLEARANCE_BETWEEN_PROBES, z_probe_fast_mm_s);\n""",
    """    if (raise_after == PROBE_PT_RAISE) {\n      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n        do_blocking_move_to_z(current_position.z + float(m8_mesh_safe_z), z_probe_fast_mm_s);\n      #else\n        do_blocking_move_to_z(current_position.z + Z_CLEARANCE_BETWEEN_PROBES, z_probe_fast_mm_s);\n      #endif\n    }\n""",
    "runtime MicroProbe between-point clearance",
)

# ---------------------------------------------------------------------------
# Record why a physical probe cycle failed, so G29 can show it on the LCD.
# ---------------------------------------------------------------------------
replace_once(
    probe,
    """float Probe::run_z_probe(const bool sanity_check/*=true*/) {\n  DEBUG_SECTION(log_probe, \"Probe::run_z_probe\", DEBUGGING(LEVELING));\n""",
    """float Probe::run_z_probe(const bool sanity_check/*=true*/) {\n  DEBUG_SECTION(log_probe, \"Probe::run_z_probe\", DEBUGGING(LEVELING));\n  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    m8_probe_fail_reason = 0;\n  #endif\n""",
    "reset MicroProbe failure reason",
)

replace_once(
    probe,
    """    if (PROBE_TRIGGERED()) {\n      SERIAL_ERROR_MSG(\"MicroProbe triggered before Z move\");\n      LCD_ALERTMESSAGE_F(\"Probe state error\");\n      return true;\n    }\n""",
    """    if (PROBE_TRIGGERED()) {\n      m8_probe_fail_reason = 1;\n      SERIAL_ERROR_MSG(\"MicroProbe triggered before Z move\");\n      return true;\n    }\n""",
    "record pre-trigger failure",
)

replace_once(
    probe,
    """    return probe_fail || early_fail;\n  };\n""",
    """    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n      if (!m8_probe_fail_reason) {\n        if (probe_fail) m8_probe_fail_reason = 2;\n        else if (early_fail) m8_probe_fail_reason = 3;\n      }\n    #endif\n    return probe_fail || early_fail;\n  };\n""",
    "record no-trigger / early-trigger failure",
)

# ---------------------------------------------------------------------------
# G29 LCD diagnostics: live point + coordinates, and persistent stop reason.
# ---------------------------------------------------------------------------
replace_once(
    g29,
    """#include \"../../../core/debug_out.h\"\n\n#if ABL_USES_GRID\n""",
    """#include \"../../../core/debug_out.h\"\n\n#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n#endif\n\n#if ABL_USES_GRID\n""",
    "G29 MicroProbe LCD externs",
)

replace_once(
    g29,
    """          if (abl.verbose_level) SERIAL_ECHOLNPGM(\"Probing mesh point \", pt_index, \"/\", abl.abl_points, \".\");\n          TERN_(HAS_STATUS_MESSAGE, ui.status_printf(0, F(S_FMT \" %i/%i\"), GET_TEXT(MSG_PROBING_POINT), int(pt_index), int(abl.abl_points)));\n\n          abl.measured_z = faux ? 0.001f * random(-100, 101) : probe.probe_at_point(abl.probePos, raise_after, abl.verbose_level);\n\n          if (isnan(abl.measured_z)) {\n            set_bed_leveling_enabled(abl.reenable);\n            break; // Breaks out of both loops\n          }\n""",
    """          if (abl.verbose_level) SERIAL_ECHOLNPGM(\"Probing mesh point \", pt_index, \"/\", abl.abl_points, \".\");\n          #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n            m8_mesh_last_point = pt_index;\n            m8_mesh_last_x = int16_t(abl.probePos.x);\n            m8_mesh_last_y = int16_t(abl.probePos.y);\n            ui.status_printf(99, F(\"P%i/%i X%i Y%i\"), int(pt_index), int(abl.abl_points), int(m8_mesh_last_x), int(m8_mesh_last_y));\n          #else\n            TERN_(HAS_STATUS_MESSAGE, ui.status_printf(0, F(S_FMT \" %i/%i\"), GET_TEXT(MSG_PROBING_POINT), int(pt_index), int(abl.abl_points)));\n          #endif\n\n          abl.measured_z = faux ? 0.001f * random(-100, 101) : probe.probe_at_point(abl.probePos, raise_after, abl.verbose_level);\n\n          if (isnan(abl.measured_z)) {\n            set_bed_leveling_enabled(abl.reenable);\n            #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n              if (m8_probe_fail_reason == 1) ui.set_status(F(\"MESH FAIL: PRETRIGGER\"), 99);\n              else if (m8_probe_fail_reason == 2) ui.set_status(F(\"MESH FAIL: NO TRIGGER\"), 99);\n              else if (m8_probe_fail_reason == 3) ui.set_status(F(\"MESH FAIL: EARLY TRIG\"), 99);\n              else ui.set_status(F(\"MESH FAIL: PROBE\"), 99);\n            #endif\n            break; // Breaks out of both loops\n          }\n""",
    "live LCD mesh point and failure reason",
)

replace_once(
    g29,
    """    TERN_(HAS_STATUS_MESSAGE, ui.reset_status());\n\n    // Stow the probe. No raise for FIX_MOUNTED_PROBE.\n""",
    """    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n      if (!isnan(abl.measured_z))\n        ui.status_printf(99, F(\"MESH OK %i/%i\"), int(abl.abl_points), int(abl.abl_points));\n    #else\n      TERN_(HAS_STATUS_MESSAGE, ui.reset_status());\n    #endif\n\n    // Stow the probe. No raise for FIX_MOUNTED_PROBE.\n""",
    "preserve LCD mesh result",
)

# ---------------------------------------------------------------------------
# Bed Level Setup: adjustable safe Z and a button to recall the last result.
# ---------------------------------------------------------------------------
replace_once(
    bed,
    """#include \"../../gcode/queue.h\"\n""",
    """#include \"../../gcode/queue.h\"\n\n#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  extern int16_t m8_mesh_safe_z;\n  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;\n  extern int16_t m8_mesh_last_x, m8_mesh_last_y;\n#endif\n""",
    "Bed Level Setup MicroProbe LCD externs",
)

# Convert the hard-coded Z15 move from the reliability patch to the LCD value.
replace_once(
    bed,
    """    PSTR(\"G28 Z\\nG90\\nG1 Z15 F600\\nG29 P%u L10 R%i F10 B%i E V1\"),\n    points, int(map_right), int(map_back)\n""",
    """    PSTR(\"G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L10 R%i F10 B%i E V1\"),\n    int(m8_mesh_safe_z), points, int(map_right), int(map_back)\n""",
    "runtime LCD safe-Z G29 command",
)

replace_once(
    bed,
    """  ui.set_status(F(\"Mesh: Z15 safe travel\"));\n""",
    """  ui.status_printf(99, F(\"Mesh Safe Z %imm\"), int(m8_mesh_safe_z));\n""",
    "runtime safe-Z start status",
)

# Helper lets the user recall the last result without a computer.
replace_once(
    bed,
    """static void m8_run_mesh_3() { m8_run_sized_mesh(3); }\n""",
    """static void m8_show_last_mesh() {\n  if (!m8_mesh_last_point) ui.set_status(F(\"No mesh run yet\"), 99);\n  else if (m8_probe_fail_reason == 1) ui.status_printf(99, F(\"P%i X%i Y%i PRETRIG\"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));\n  else if (m8_probe_fail_reason == 2) ui.status_printf(99, F(\"P%i X%i Y%i NO TRIG\"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));\n  else if (m8_probe_fail_reason == 3) ui.status_printf(99, F(\"P%i X%i Y%i EARLY\"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));\n  else ui.status_printf(99, F(\"Last P%i X%i Y%i OK\"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));\n  ui.return_to_status();\n}\n\nstatic void m8_run_mesh_3() { m8_run_sized_mesh(3); }\n""",
    "last mesh result helper",
)

replace_once(
    bed,
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 40, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 40, 914);\n    ACTION_ITEM_F(F(\"Run 3x3 Mesh\"), m8_run_mesh_3);\n""",
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 40, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 40, 914);\n    EDIT_ITEM_F(int3, F(\"Mesh Safe Z mm\"), &m8_mesh_safe_z, 6, 20);\n    ACTION_ITEM_F(F(\"Show Last Mesh\"), m8_show_last_mesh);\n    ACTION_ITEM_F(F(\"Run 3x3 Mesh\"), m8_run_mesh_3);\n""",
    "LCD safe-Z and last-result controls",
)

print("Added LCD Mesh Safe Z, live point/XY diagnostics, persistent failure reason, and corrected MicroProbe deploy/stow lift")
