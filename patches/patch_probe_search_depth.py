from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
probe = root / "src/module/probe.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"

# Add a separate LCD-adjustable search depth. This is intentionally independent
# from Mesh Safe Z: Safe Z controls clearance above the bed, while Search Depth
# controls how far below the expected trigger height probing may continue.
replace_once(
    probe,
    "  int16_t m8_mesh_safe_z = 10;      // LCD adjustable 6..20 mm\n",
    "  int16_t m8_mesh_safe_z = 10;      // LCD adjustable 6..20 mm\n  int16_t m8_probe_search_mm = 4;    // LCD adjustable 2..8 mm\n",
    "probe search depth global",
)

# Marlin 2.1.2.8 normally stops at Z_PROBE_LOW_POINT (-2mm) below the expected
# trigger height. On this large bed that can be too shallow if the bed differs
# by more than 2mm from the Z-home point. Use the LCD-selected depth instead.
replace_once(
    probe,
    "  const float z_probe_low_point = axis_is_trusted(Z_AXIS) ? -offset.z + Z_PROBE_LOW_POINT : -10.0;\n",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
    const float z_probe_low_point = axis_is_trusted(Z_AXIS) ? -offset.z - float(m8_probe_search_mm) : -10.0;
  #else
    const float z_probe_low_point = axis_is_trusted(Z_AXIS) ? -offset.z + Z_PROBE_LOW_POINT : -10.0;
  #endif
""",
    "runtime probe search low point",
)

# Expose the setting in Bed Level Setup.
replace_once(
    bed,
    "  extern int16_t m8_mesh_safe_z;\n",
    "  extern int16_t m8_mesh_safe_z, m8_probe_search_mm;\n",
    "Bed Level Setup search-depth extern",
)

replace_once(
    bed,
    "    EDIT_ITEM_F(int3, F(\"Mesh Safe Z mm\"), &m8_mesh_safe_z, 6, 20);\n",
    "    EDIT_ITEM_F(int3, F(\"Mesh Safe Z mm\"), &m8_mesh_safe_z, 6, 20);\n    EDIT_ITEM_F(int3, F(\"Probe Search mm\"), &m8_probe_search_mm, 2, 8);\n",
    "LCD probe search depth item",
)

print("Added LCD Probe Search mm setting: default 4mm, adjustable 2..8mm")
