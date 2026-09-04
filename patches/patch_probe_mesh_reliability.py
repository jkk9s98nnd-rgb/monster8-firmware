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

# ---------------------------------------------------------------------------
# 1) BIQU MicroProbe V2 cold-start reliability
# ---------------------------------------------------------------------------
# The first deploy after power-up gets an explicit off/on/off conditioning
# cycle before normal probe deployment. This makes the first G28 Z start from
# the same known electrical state as later probe cycles.
replace_once(
    probe,
    """  if (endstops.z_probe_enabled == deploy) return false;\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    static bool m8_probe_conditioned = false;\n    if (deploy && !m8_probe_conditioned) {\n      // Cold-start conditioning: force a complete disable / enable / disable\n      // sequence and allow the probe electronics to settle before the first\n      // real deployment. No Z motion occurs during this sequence.\n      endstops.enable_z_probe(false);\n      safe_delay(250);\n      endstops.enable_z_probe(true);\n      safe_delay(500);\n      endstops.enable_z_probe(false);\n      safe_delay(250);\n      m8_probe_conditioned = true;\n    }\n  #endif\n\n  if (endstops.z_probe_enabled == deploy) return false;\n""",
    "cold-start MicroProbe conditioning",
)

# Give every enable edge enough settling time for the MicroProbe V2 trigger
# electronics. Also give the stow edge a short settle period before the next
# deploy. This is intentionally conservative because this machine has already
# shown a first-cycle miss after power-up.
replace_once(
    endstops,
    """        if (onoff) safe_delay(50);\n""",
    """        safe_delay(onoff ? 500 : 200);\n""",
    "MicroProbe wake delay",
)

# Refuse a normal probing descent if the input is already reporting TRIGGERED
# immediately after deployment. This catches a bad / floating / stuck input
# before motion begins during G29 probing.
replace_once(
    probe,
    """  // Disable stealthChop if used. Enable diag1 pin on driver.\n""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    if (PROBE_TRIGGERED()) {\n      SERIAL_ERROR_MSG(\"MicroProbe triggered before Z move\");\n      LCD_ALERTMESSAGE_F(\"Probe state error\");\n      return true;\n    }\n  #endif\n\n  // Disable stealthChop if used. Enable diag1 pin on driver.\n""",
    "pre-descent probe-state safety",
)

# ---------------------------------------------------------------------------
# 2) Temporary G29 area reliability
# ---------------------------------------------------------------------------
# The previous custom command used L0/F0. Marlin's normal probing limits reject
# those bounds, so what looked like the first mesh point was actually only
# G28 Z; G29 then returned immediately and M500 printed "Settings Stored".
# Keep a 10mm probing inset inside the user-selected temporary map.
replace_once(
    bed,
    """static void m8_run_sized_mesh(const uint8_t points) {\n  char cmd[80];\n  snprintf_P(\n    cmd, sizeof(cmd),\n    PSTR(\"G28 Z\\nG29 P%u L0 R%i F0 B%i E V1\\nM500\"),\n    points, int(m8_mesh_x_mm), int(m8_mesh_y_mm)\n  );\n  queue.inject(cmd);\n}\n""",
    """static void m8_run_sized_mesh(const uint8_t points) {\n  // Marlin normally keeps the probe away from the physical bed edge.\n  // The selected Map X / Map Y dimensions still describe the temporary\n  // work area from XY zero, but probing is inset 10mm on all four sides.\n  const int16_t map_right = m8_mesh_x_mm - 10,\n                map_back  = m8_mesh_y_mm - 10;\n  char cmd[96];\n  snprintf_P(\n    cmd, sizeof(cmd),\n    PSTR(\"G28 Z\\nG29 P%u L10 R%i F10 B%i E V1\\nM500\"),\n    points, int(map_right), int(map_back)\n  );\n  ui.set_status(F(\"Mesh: Home Z then probe\"));\n  queue.inject(cmd);\n}\n""",
    "safe temporary mesh bounds",
)

# A map smaller than 40mm leaves too little usable space after the 10mm inset.
replace_once(
    bed,
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 20, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 20, 914);\n""",
    """    EDIT_ITEM_F(int3, F(\"Map X mm\"), &m8_mesh_x_mm, 40, 610);\n    EDIT_ITEM_F(int3, F(\"Map Y mm\"), &m8_mesh_y_mm, 40, 914);\n""",
    "minimum temporary mesh size",
)

print("Applied MicroProbe cold-start conditioning, 500ms settle, and corrected G29 temporary-map bounds")
