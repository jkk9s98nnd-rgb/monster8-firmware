from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


menu = Path("MarlinSource/Marlin/src/lcd/menu/menu_bed_leveling.cpp")

# The automatic mesh menu needs to build a G29 command at runtime from the
# temporary X/Y map dimensions selected on the LCD.
replace_once(
    menu,
    '#include "../../feature/bedlevel/bedlevel.h"\n',
    '#include "../../feature/bedlevel/bedlevel.h"\n#include "../../gcode/queue.h"\n',
    "mesh area command queue include",
)

mesh_area_helpers = r'''
// --------------------------------------------------------------------------
// Monster8 temporary probing area
// --------------------------------------------------------------------------
// This does NOT change the physical machine size. It only limits G29 travel.
// The user manually places the nozzle at the lower-left corner of the area and
// sets X0/Y0. G29 then probes from X0/Y0 to the selected X/Y size.
// Defaults are intentionally conservative while the Sprite cable is short.
static int16_t m8_mesh_x_mm = 100;
static int16_t m8_mesh_y_mm = 100;

static void m8_run_sized_mesh(const uint8_t points) {
  char cmd[80];
  snprintf_P(
    cmd, sizeof(cmd),
    PSTR("G28 Z\nG29 P%u L0 R%i F0 B%i\nM500"),
    points, int(m8_mesh_x_mm), int(m8_mesh_y_mm)
  );
  queue.inject(cmd);
}

static void m8_run_mesh_3() { m8_run_sized_mesh(3); }
static void m8_run_mesh_5() { m8_run_sized_mesh(5); }
static void m8_run_mesh_7() { m8_run_sized_mesh(7); }

'''

replace_once(
    menu,
    "void menu_bed_leveling() {\n",
    mesh_area_helpers + "void menu_bed_leveling() {\n",
    "temporary mesh area helpers",
)

old_mesh_items = r'''    GCODES_ITEM_F(F("Run 3x3 Mesh"), F("G28 Z\nG29 P3\nM500"));
    GCODES_ITEM_F(F("Run 5x5 Mesh"), F("G28 Z\nG29 P5\nM500"));
    GCODES_ITEM_F(F("Run 7x7 Mesh"), F("G28 Z\nG29 P7\nM500"));
    GCODES_ITEM_F(F("Leveling ON"),  F("M420 S1"));
    GCODES_ITEM_F(F("Leveling OFF"), F("M420 S0"));
'''

new_mesh_items = r'''    STATIC_ITEM_F(F("Map starts at X0 Y0"));
    EDIT_ITEM_F(int3, F("Map X mm"), &m8_mesh_x_mm, 20, 610);
    EDIT_ITEM_F(int3, F("Map Y mm"), &m8_mesh_y_mm, 20, 914);
    ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);
    ACTION_ITEM_F(F("Run 5x5 Mesh"), m8_run_mesh_5);
    ACTION_ITEM_F(F("Run 7x7 Mesh"), m8_run_mesh_7);
    GCODES_ITEM_F(F("Leveling ON"),  F("M420 S1"));
    GCODES_ITEM_F(F("Leveling OFF"), F("M420 S0"));
'''

replace_once(
    menu,
    old_mesh_items,
    new_mesh_items,
    "LCD temporary mesh area controls",
)

print("Added LCD temporary G29 area controls: Map X / Map Y from X0 Y0")
