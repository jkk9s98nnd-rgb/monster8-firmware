from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
main = root / "src/lcd/menu/menu_main.cpp"

# Restore the bed map variables to the exact private/static form used by the
# last known-good leveling build. The mapped-cube patch had changed these to
# external globals only so menu_main could read them.
text = bed.read_text()
replace_pairs = [
    ("int16_t m8_mesh_x_mm = 100;", "static int16_t m8_mesh_x_mm = 100;", "restore static Map X"),
    ("int16_t m8_mesh_y_mm = 100;", "static int16_t m8_mesh_y_mm = 100;", "restore static Map Y"),
]
for old, new, label in replace_pairs:
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found")
    text = text.replace(old, new, 1)

# Expose read-only accessors instead of exporting the bed-level state itself.
anchor = "static int16_t m8_mesh_y_mm = 100;\n"
if anchor not in text:
    raise SystemExit("bed map getter insertion point not found")
text = text.replace(
    anchor,
    anchor + "\nint16_t monster8_mesh_map_x() { return m8_mesh_x_mm; }\nint16_t monster8_mesh_map_y() { return m8_mesh_y_mm; }\n",
    1,
)
bed.write_text(text)

# The cube now calls the read-only accessors. No bed-level variable is shared.
text = main.read_text()
old = "extern int16_t m8_mesh_x_mm, m8_mesh_y_mm;"
new = "extern int16_t monster8_mesh_map_x();\nextern int16_t monster8_mesh_map_y();"
if old not in text:
    raise SystemExit("mapped cube extern variables not found")
text = text.replace(old, new, 1)

old = "int16_t v = m8_mesh_x_mm < m8_mesh_y_mm ? m8_mesh_x_mm : m8_mesh_y_mm;"
new = "const int16_t map_x = monster8_mesh_map_x(), map_y = monster8_mesh_map_y();\n  int16_t v = map_x < map_y ? map_x : map_y;"
if old not in text:
    raise SystemExit("mapped cube max-size calculation not found")
text = text.replace(old, new, 1)
main.write_text(text)

print("Restored isolated bed-map state and switched cube sizing to read-only accessors")
