from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


bed = Path("MarlinSource/Marlin/src/lcd/menu/menu_bed_leveling.cpp")
motion = Path("MarlinSource/Marlin/src/lcd/menu/menu_motion.cpp")
main = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")

# ---------------------------------------------------------------------------
# Bed Level Setup: everything needed in one place
# ---------------------------------------------------------------------------
bed_text = bed.read_text()
old = 'PSTR("G28 Z\\nG29 P%u L0 R%i F0 B%i\\nM500"),'
new = 'PSTR("G28 Z\\nG29 P%u L0 R%i F0 B%i E V1\\nM500"),'
if old not in bed_text:
    raise SystemExit("mesh probe-each-point command not found")
bed_text = bed_text.replace(old, new, 1)

needle = """  START_MENU();
  BACK_ITEM(MSG_MOTION);

  // This machine has no X/Y homing switches. Never offer plain G28.
"""
insert = """  START_MENU();
  BACK_ITEM(MSG_MOTION);
  STATIC_ITEM_F(F("BED LEVEL SETUP"));
  GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));
  GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));

  // This machine has no X/Y homing switches. Never offer plain G28.
"""
if needle not in bed_text:
    raise SystemExit("bed-level menu insertion point not found")
bed_text = bed_text.replace(needle, insert, 1)
bed.write_text(bed_text)

# ---------------------------------------------------------------------------
# Never let an LCD Auto Home command try X/Y switches on this machine.
# Any ordinary Auto Home menu entry becomes Z-only probe homing.
# ---------------------------------------------------------------------------
motion_text = motion.read_text()
old_home = 'GCODES_ITEM(MSG_AUTO_HOME, FPSTR(G28_STR));'
count = motion_text.count(old_home)
if count < 2:
    raise SystemExit(f"expected multiple Auto Home items, found {count}")
motion_text = motion_text.replace(old_home, 'GCODES_ITEM_F(F("Home Z Only"), F("G28 Z"));')
motion.write_text(motion_text)

# ---------------------------------------------------------------------------
# Setup Test Print polish
#  - 1..3 adjustable prime lines
#  - adjustable prime length and prime extrusion
#  - prime lines parked farther from cube
#  - flow percentage, editable before and during print
#  - speed editable during print
#  - STOP lifts 5mm, parks at XY zero, shuts heater off
# ---------------------------------------------------------------------------
main_text = main.read_text()

main_text = main_text.replace(
    "  M8TC_PRIME_LINE2,\n  M8TC_PRIME_TO_CUBE,",
    "  M8TC_PRIME_LINE2,\n  M8TC_PRIME_LINE3,\n  M8TC_PRIME_TO_CUBE,",
    1,
)

old_vars = """static int16_t m8tc_temp = 230;
static int16_t m8tc_size = 10;       // cube X/Y/Z size in mm
static int16_t m8tc_speed = 25;      // print speed in mm/s
static uint8_t m8tc_nozzle = 2;      // 0=.4mm, 1=.6mm, 2=.8mm
"""
new_vars = """static int16_t m8tc_temp = 230;
static int16_t m8tc_size = 10;       // cube X/Y/Z size in mm
static int16_t m8tc_speed = 25;      // print speed in mm/s
static int16_t m8tc_flow = 100;      // live cube extrusion percentage
static int16_t m8tc_prime_lines = 2; // 1..3 priming lines
static int16_t m8tc_prime_len = 25;  // line length in mm
static int16_t m8tc_prime_pct = 120; // prime extrusion percentage
static uint8_t m8tc_nozzle = 2;      // 0=.4mm, 1=.6mm, 2=.8mm
"""
if old_vars not in main_text:
    raise SystemExit("test-cube variable block not found")
main_text = main_text.replace(old_vars, new_vars, 1)

old_counts = """static uint8_t m8tc_bottom_layers, m8tc_edge,
               m8tc_infill_index, m8tc_infill_count;
static int8_t m8tc_infill_dir;
"""
new_counts = """static uint8_t m8tc_bottom_layers, m8tc_edge,
               m8tc_infill_index, m8tc_infill_count, m8tc_prime_done;
static int8_t m8tc_infill_dir;
"""
if old_counts not in main_text:
    raise SystemExit("test-cube counter block not found")
main_text = main_text.replace(old_counts, new_counts, 1)

old_prime_profile = """  // Two priming lines. At least 20mm long, or cube width if larger.
  m8tc_prime_length = m8tc_size > 20 ? float(m8tc_size) : 20.0f;
"""
new_prime_profile = """  // Priming is user adjustable from the LCD.
  m8tc_prime_length = float(m8tc_prime_len);
"""
if old_prime_profile not in main_text:
    raise SystemExit("prime profile block not found")
main_text = main_text.replace(old_prime_profile, new_prime_profile, 1)

old_start = """  m8tc_layer = 0;
  m8tc_x = m8tc_y = 0;
  m8tc_state = M8TC_HOME_Z;
"""
new_start = """  m8tc_layer = 0;
  m8tc_x = m8tc_y = 0;
  m8tc_prime_done = 0;
  m8tc_state = M8TC_HOME_Z;
"""
if old_start not in main_text:
    raise SystemExit("test start block not found")
main_text = main_text.replace(old_start, new_start, 1)

# Helpers scale extrusion live, so changing Flow while the cube is running
# affects subsequent extrusion moves without changing E-steps.
marker = """static void m8tc_start() {
"""
helpers = """static float m8tc_flow_scale() { return float(m8tc_flow) * 0.01f; }
static float m8tc_prime_scale() { return float(m8tc_prime_pct) * 0.01f * m8tc_flow_scale(); }

static void m8tc_start() {
"""
if marker not in main_text:
    raise SystemExit("test helper insertion point not found")
main_text = main_text.replace(marker, helpers, 1)

old_stop = """static void m8tc_stop() {
  m8tc_state = M8TC_IDLE;
  queue.inject_P(nullptr);
  queue.clear();
  quickstop_stepper();
  thermalManager.disable_all_heaters();

  // Restore the normal slicer coordinate modes after an interrupted test.
  queue.inject(F("G90\\nM82\\nM107"));
  ui.set_status(F("Test Cube Stopped"));
  ui.completion_feedback();
  ui.return_to_status();
}
"""
new_stop = """static void m8tc_stop() {
  m8tc_state = M8TC_IDLE;
  queue.inject_P(nullptr);
  queue.clear();
  quickstop_stepper();
  thermalManager.disable_all_heaters();

  // Abort safely: lift before any XY travel, then park at the manually-set
  // work origin. This prevents the nozzle scraping across the stopped print.
  queue.inject(F("G91\\nG1 Z5 F600\\nG90\\nG1 X0 Y0 F3000\\nM82\\nM107"));
  ui.set_status(F("Stopped: Lift / Park"));
  ui.completion_feedback();
  ui.return_to_status();
}
"""
if old_stop not in main_text:
    raise SystemExit("test stop function not found")
main_text = main_text.replace(old_stop, new_stop, 1)

old_prime_states = """    case M8TC_PRIME_LINE1: {
      const float e = m8tc_prime_length * m8tc_e_per_mm * 1.15f;
      if (m8tc_enqueue_axis_e('X', m8tc_prime_length, e, 600))
        m8tc_state = M8TC_PRIME_STEP;
    } break;

    case M8TC_PRIME_STEP:
      if (m8tc_enqueue_xy(0, 1.5f, 1200))
        m8tc_state = M8TC_PRIME_LINE2;
      break;

    case M8TC_PRIME_LINE2: {
      const float e = m8tc_prime_length * m8tc_e_per_mm * 1.15f;
      if (m8tc_enqueue_axis_e('X', -m8tc_prime_length, e, 600))
        m8tc_state = M8TC_PRIME_TO_CUBE;
    } break;

    case M8TC_PRIME_TO_CUBE:
      // Move 2mm beyond the second prime line. This makes the cube start
      // 3.5mm in +Y from the original current XY point.
      if (m8tc_enqueue_xy(0, 2.0f, 1800)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_OUTER_START;
        ui.set_status(F("Printing Test Cube"));
      }
      break;
"""
new_prime_states = """    case M8TC_PRIME_LINE1: {
      const float e = m8tc_prime_length * m8tc_e_per_mm * m8tc_prime_scale();
      if (m8tc_enqueue_axis_e('X', m8tc_prime_length, e, 600)) {
        m8tc_prime_done = 1;
        m8tc_state = m8tc_prime_lines <= 1 ? M8TC_PRIME_TO_CUBE : M8TC_PRIME_STEP;
      }
    } break;

    case M8TC_PRIME_STEP:
      if (m8tc_enqueue_xy(0, 2.0f, 1200))
        m8tc_state = m8tc_prime_done == 1 ? M8TC_PRIME_LINE2 : M8TC_PRIME_LINE3;
      break;

    case M8TC_PRIME_LINE2: {
      const float e = m8tc_prime_length * m8tc_e_per_mm * m8tc_prime_scale();
      if (m8tc_enqueue_axis_e('X', -m8tc_prime_length, e, 600)) {
        m8tc_prime_done = 2;
        m8tc_state = m8tc_prime_lines <= 2 ? M8TC_PRIME_TO_CUBE : M8TC_PRIME_STEP;
      }
    } break;

    case M8TC_PRIME_LINE3: {
      const float e = m8tc_prime_length * m8tc_e_per_mm * m8tc_prime_scale();
      if (m8tc_enqueue_axis_e('X', m8tc_prime_length, e, 600)) {
        m8tc_prime_done = 3;
        m8tc_state = M8TC_PRIME_TO_CUBE;
      }
    } break;

    case M8TC_PRIME_TO_CUBE:
      // Leave a generous gap between the priming lines and the test cube so
      // the purge is easy to see and cannot merge into the first layer.
      if (m8tc_enqueue_xy(0, 18.0f, 1800)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_OUTER_START;
        ui.set_status(F("Printing Test Cube"));
      }
      break;
"""
if old_prime_states not in main_text:
    raise SystemExit("prime state block not found")
main_text = main_text.replace(old_prime_states, new_prime_states, 1)

# Apply live flow to cube walls and infill. There are two wall occurrences.
wall_old = "const float e = side * m8tc_e_per_mm;"
wall_count = main_text.count(wall_old)
if wall_count != 2:
    raise SystemExit(f"expected 2 wall extrusion calculations, found {wall_count}")
main_text = main_text.replace(wall_old, "const float e = side * m8tc_e_per_mm * m8tc_flow_scale();")

infill_old = "const float e = m8tc_infill_span * m8tc_e_per_mm;"
if infill_old not in main_text:
    raise SystemExit("infill extrusion calculation not found")
main_text = main_text.replace(infill_old, "const float e = m8tc_infill_span * m8tc_e_per_mm * m8tc_flow_scale();", 1)

old_idle_menu = """    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, 30);
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);

    if (m8tc_nozzle == 0)
"""
new_idle_menu = """    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, 30);
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);
    EDIT_ITEM_F(int3, F("Flow %"), &m8tc_flow, 50, 150);
    EDIT_ITEM_F(int3, F("Prime Lines"), &m8tc_prime_lines, 1, 3);
    EDIT_ITEM_F(int3, F("Prime Length"), &m8tc_prime_len, 10, 60);
    EDIT_ITEM_F(int3, F("Prime Extrude %"), &m8tc_prime_pct, 80, 200);

    if (m8tc_nozzle == 0)
"""
if old_idle_menu not in main_text:
    raise SystemExit("idle test menu block not found")
main_text = main_text.replace(old_idle_menu, new_idle_menu, 1)

old_run_menu = """  else {
    STATIC_ITEM_F(F("Setup Test Running"));
    ACTION_ITEM_F(F("Z Closer -0.05"), m8tc_z_closer);
    ACTION_ITEM_F(F("Z Farther +0.05"), m8tc_z_farther);
    ACTION_ITEM_F(F("STOP TEST"), m8tc_stop);
  }
"""
new_run_menu = """  else {
    STATIC_ITEM_F(F("Setup Test Running"));
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);
    EDIT_ITEM_F(int3, F("Flow %"), &m8tc_flow, 50, 150);
    ACTION_ITEM_F(F("Z Closer -0.05"), m8tc_z_closer);
    ACTION_ITEM_F(F("Z Farther +0.05"), m8tc_z_farther);
    ACTION_ITEM_F(F("STOP: Lift + Park"), m8tc_stop);
  }
"""
if old_run_menu not in main_text:
    raise SystemExit("running test menu block not found")
main_text = main_text.replace(old_run_menu, new_run_menu, 1)

main.write_text(main_text)

print("Applied Monster8 combined polish: probe-each-point mesh, bed setup center, safe Z-only home, adjustable prime/flow, and safe stop park")
