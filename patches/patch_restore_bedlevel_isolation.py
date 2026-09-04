from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
main = root / "src/lcd/menu/menu_main.cpp"

# Restore the exact private/static map variables used by the last known-good
# bed-leveling build. The test-cube feature must not own or directly link to
# bed-level state.
replace_once(
    bed,
    "int16_t m8_mesh_x_mm = 100;\nint16_t m8_mesh_y_mm = 100;\n",
    """static int16_t m8_mesh_x_mm = 100;
static int16_t m8_mesh_y_mm = 100;

// Read-only access for the standalone test-print menu. These functions do not
// alter probing state or the mesh runner.
int16_t m8_get_mesh_x_mm() { return m8_mesh_x_mm; }
int16_t m8_get_mesh_y_mm() { return m8_mesh_y_mm; }
""",
    "restore private map variables",
)

# The cube reads the current map dimensions only through the accessors.
replace_once(
    main,
    "extern int16_t m8_mesh_x_mm, m8_mesh_y_mm;\n",
    "extern int16_t m8_get_mesh_x_mm();\nextern int16_t m8_get_mesh_y_mm();\n",
    "replace direct mesh variable linkage",
)

replace_once(
    main,
    "  int16_t v = m8_mesh_x_mm < m8_mesh_y_mm ? m8_mesh_x_mm : m8_mesh_y_mm;\n",
    "  const int16_t mx = m8_get_mesh_x_mm(), my = m8_get_mesh_y_mm();\n  int16_t v = mx < my ? mx : my;\n",
    "cube map getter usage",
)

# Regression guard: the known-good mesh command path must still be present.
text = bed.read_text()
required = 'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L10 R%i F10 B%i E V1")'
if required not in text:
    raise SystemExit("known-good G28 Z -> safe-Z -> G29 mesh path was changed")

print("Restored bed-level map state isolation; cube now uses read-only map getters")
