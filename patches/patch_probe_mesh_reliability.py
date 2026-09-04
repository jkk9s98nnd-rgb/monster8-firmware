from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
probe = root / "src/module/probe.cpp"
endstops = root / "src/module/endstops.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
config = root / "Configuration.h"
g29 = root / "src/gcode/bedlevel/abl/G29.cpp"

# ---------------------------------------------------------------------------
# 1) BIQU MicroProbe V2 cold-start reliability
# ---------------------------------------------------------------------------
replace_once(
    probe,
    """  if (endstops.z_probe_enabled == deploy) return false;\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    static bool m8_probe_conditioned = false;\n    if (deploy && !m8_probe_conditioned) {\n      endstops.enable_z_probe(false);\n      safe_delay(250);\n      endstops.enable_z_probe(true);\n      safe_delay(500);\n      endstops.enable_z_probe(false);\n      safe_delay(250);\n      m8_probe_conditioned = true;\n    }\n  #endif\n\n  if (endstops.z_probe_enabled == deploy) return false;\n""",
    "cold-start MicroProbe conditioning",
)

replace_once(
    endstops,
    """        if (onoff) safe_delay(50);\n""",
    """        safe_delay(onoff ? 500 : 200);\n""",
    "MicroProbe wake delay",
)

# Runtime safe-Z value shared with the LCD bed-level menu.
replace_once(
    probe,
    """bool Probe::set_deployed(const bool deploy) {\n""",
    """#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n  int16_t m8_mesh_safe_z = 10;\n  static uint8_t m8_probe_fail_reason = 0; // 1=triggered before move, 2=no trigger\n#endif\n\nbool Probe::set_deployed(const bool deploy) {\n""",
    "MicroProbe runtime mesh safe Z",
)

# IMPORTANT: Undo the old MicroProbe shortcut that deliberately prevented any
# Z raise during deploy/stow. That shortcut is unsafe during G29 because E
# stows/redeploys the probe at every mesh point.
replace_once(
    probe,
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    constexpr bool z_raise_wanted = false;\n  #elif ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n    const bool z_raise_wanted = deploy;\n  #else\n    constexpr bool z_raise_wanted = true;\n  #endif\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    constexpr bool z_raise_wanted = true;\n  #elif ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n    const bool z_raise_wanted = deploy;\n  #else\n    constexpr bool z_raise_wanted = true;\n  #endif\n""",
    "restore MicroProbe deploy/stow Z raise",
)

replace_once(
    probe,
    """  if (z_raise_wanted)\n    do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));\n""",
    """  if (z_raise_wanted) {\n    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n      do_z_raise(float(m8_mesh_safe_z));\n    #else\n      do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));\n    #endif\n  }\n""",
    "runtime MicroProbe deploy/stow clearance",
)

# Record and display why a MicroProbe descent was rejected / failed.
replace_once(
    probe,
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    if (PROBE_TRIGGERED()) {\n      SERIAL_ERROR_MSG(\"MicroProbe triggered before Z move\");\n      LCD_ALERTMESSAGE_F(\"Probe state error\");\n      return true;\n    }\n  #endif\n\n  // Disable stealthChop if used. Enable diag1 pin on driver.\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    m8_probe_fail_reason = 0;\n    if (PROBE_TRIGGERED()) {\n      m8_probe_fail_reason = 1;\n      SERIAL_ERROR_MSG(\"MicroProbe triggered before Z move\");\n      LCD_ALERTMESSAGE_F(\"STOP: EARLY TRIGGER\");\n      return true;\n    }\n  #endif\n\n  // Disable stealthChop if used. Enable diag1 pin on driver.\n""",
    "pre-descent probe-state diagnostic",
)

replace_once(
    probe,
    """  // Offset sensorless probing\n  #if HAS_DELTA_SENSORLESS_PROBING\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    if (!probe_triggered) m8_probe_fail_reason = 2;\n  #endif\n\n  // Offset sensorless probing\n  #if HAS_DELTA_SENSORLESS_PROBING\n""",
    "record no-trigger probe failure",
)

replace_once(
    probe,
    """  if (isnan(measured_z)) {\n    stow();\n    LCD_MESSAGE(MSG_LCD_PROBING_FAILED);\n    #if DISABLED(G29_RETRY_AND_RECOVER)\n      SERIAL_ERROR_MSG(STR_ERR_PROBING_FAILED);\n    #endif\n  }\n""",
    """  if (isnan(measured_z)) {\n    stow();\n    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n      if (m8_probe_fail_reason == 1)\n        LCD_ALERTMESSAGE_F(\"STOP: EARLY TRIGGER\");\n      else if (m8_probe_fail_reason == 2)\n        LCD_ALERTMESSAGE_F(\"STOP: NO TRIGGER\");\n      else\n        LCD_ALERTMESSAGE_F(\"STOP: PROBE FAILED\");\n    #else\n      LCD_MESSAGE(MSG_LCD_PROBING_FAILED);\n    #endif\n    #if DISABLED(G29_RETRY_AND_RECOVER)\n      SERIAL_ERROR_MSG(STR_ERR_PROBING_FAILED);\n    #endif\n  }\n""",
    "persistent LCD probe failure reason",
)

# Do not erase the failure message at the end of G29. Successful runs still
# clear the temporary "Probing Point n/N" status normally.
replace_once(
    g29,
    """    TERN_(HAS_STATUS_MESSAGE, ui.reset_status());\n\n    // Stow the probe. No raise for FIX_MOUNTED_PROBE.\n""",
    """    TERN_(HAS_STATUS_MESSAGE, if (!isnan(abl.measured_z)) ui.reset_status());\n\n    // Stow the probe. No raise for FIX_MOUNTED_PROBE.\n""",
    "preserve LCD mesh failure message",
)

# ---------------------------------------------------------------------------
# 2) Safe Z clearance for mesh probing
# ---------------------------------------------------------------------------
# Keep compile-time values conservative too. The MicroProbe path above uses
# the LCD-adjustable m8_mesh_safe_z value for actual deploy/stow clearance.
replace_once(
    config,
    """#define Z_CLEARANCE_DEPLOY_PROBE   10 // (mm) Z Clearance for Deploy/Stow\n#define Z_CLEARANCE_BETWEEN_PROBES  5 // (mm) Z Clearance between probe points\n""",
    """#define Z_CLEARANCE_DEPLOY_PROBE   10 // (mm) fallback deploy/stow clearance\n#define Z_CLEARANCE_BETWEEN_PROBES 10 // (mm) fallback between-point clearance\n""",
    "MicroProbe fallback Z clearances",
)

# ---------------------------------------------------------------------------
# 3) LCD-adjustable temporary mesh and initial safe lift
# ---------------------------------------------------------------------------
replace_once(
    bed,
    """static int16_t m8_mesh_y_mm = 100;\n""",
    """static int16_t m8_mesh_y_mm = 100;\nextern int16_t m8_mesh_safe_z;\n""",
    "LCD extern Mesh Safe Z",
)

replace_once(
    bed,
    """static void m8_run_sized_mesh(const uint8_t points) {\n  char cmd[80];\n  snprintf_P(\n    cmd, sizeof(cmd),\n    PSTR(\"G28 Z\\nG29 P%u L0 R%i F0 B%i E V1\\nM500\"),\n    points, int(m8_mesh_x_mm), int(m8_mesh_y_mm)\n  );\n  queue.inject(cmd);\n}\n""",
    """static void m8_run_sized_mesh(const uint8_t points) {\n  const int16_t map_right = m8_mesh_x_mm - 10,\n                map_back  = m8_mesh_y_mm - 10;\n  char cmd[128];\n  snprintf_P(\n    cmd, sizeof(cmd),\n    PSTR(\"G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L10 R%i F10 B%i E V1\"),\n    int(m8_mesh_safe_z), points, int(map_right), int(map_back)\n  );\n  ui.status_printf(0, F(\"Mesh Safe Z=%imm\"), int(m8_mesh_safe_z));\n  queue.inject(cmd);\n}\n""",
    "safe temporary mesh bounds and adjustable initial lift",
)

replace_once(
    bed,
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 20, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 20, 914);\n""",
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 40, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 40, 914);\n    EDIT_ITEM_F(int3, F(\"Mesh Safe Z mm\"), &m8_mesh_safe_z, 6, 20);\n""",
    "LCD Map X/Y and Mesh Safe Z controls",
)

print("Applied LCD-adjustable Mesh Safe Z, restored MicroProbe Z raise, and persistent LCD probe diagnostics")
