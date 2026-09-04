from pathlib import Path

root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
main = root / "src/lcd/menu/menu_main.cpp"

# Keep the private/static map variables used by the bed-level menu. The test
# print may read the selected size through getters, but must never mutate mesh
# state or the mesh runner directly.
bed_text = bed.read_text()
global_block = "int16_t m8_mesh_x_mm = 100;\nint16_t m8_mesh_y_mm = 100;\n"
private_block = """static int16_t m8_mesh_x_mm = 100;
static int16_t m8_mesh_y_mm = 100;

// Read-only access for the standalone test-print menu. These functions do not
// alter probing state or the mesh runner.
int16_t m8_get_mesh_x_mm() { return m8_mesh_x_mm; }
int16_t m8_get_mesh_y_mm() { return m8_mesh_y_mm; }
"""

if global_block in bed_text:
    bed_text = bed_text.replace(global_block, private_block, 1)
elif "static int16_t m8_mesh_x_mm = 100;" in bed_text and "int16_t m8_get_mesh_x_mm()" in bed_text:
    pass
else:
    raise SystemExit("bed-level private map state / getter layout not recognized")
bed.write_text(bed_text)

main_text = main.read_text()
direct = "extern int16_t m8_mesh_x_mm, m8_mesh_y_mm;\n"
getters = "extern int16_t m8_get_mesh_x_mm();\nextern int16_t m8_get_mesh_y_mm();\n"
if direct in main_text:
    main_text = main_text.replace(direct, getters, 1)
elif getters in main_text:
    pass
else:
    raise SystemExit("test-print map accessor declarations not recognized")

direct_use = "  int16_t v = m8_mesh_x_mm < m8_mesh_y_mm ? m8_mesh_x_mm : m8_mesh_y_mm;\n"
getter_use = "  const int16_t mx = m8_get_mesh_x_mm(), my = m8_get_mesh_y_mm();\n  int16_t v = mx < my ? mx : my;\n"
if direct_use in main_text:
    main_text = main_text.replace(direct_use, getter_use, 1)
elif "m8_get_mesh_x_mm()" in main_text and "int16_t v = mx < my ? mx : my;" in main_text:
    pass
else:
    raise SystemExit("test-print map getter usage not recognized")
main.write_text(main_text)

# Regression guards. The mesh runner must preserve the proven motion path:
# - home Z only
# - raise to the LCD-selected safe Z
# - start probing at the 10mm inset, never exactly X0/Y0
# - use the selected Map X / Map Y as the outer limits
# - save a successful mesh
check = bed.read_text()
required_parts = [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'map_right = m8_mesh_x_mm,',
    'map_back  = m8_mesh_y_mm;',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500")',
    'ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);',
]
for part in required_parts:
    if part not in check:
        raise SystemExit(f"mesh regression guard failed: {part}")

print("Verified native XY zero plus known-good 10mm mesh inset")
