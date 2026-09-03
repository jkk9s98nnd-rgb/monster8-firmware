from pathlib import Path

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))

menu = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
core = Path("MarlinSource/Marlin/src/MarlinCore.cpp")

# The setup-cube feature needs direct motion access for STOP and the active
# bilinear mesh when one has already been created.
replace_once(
    menu,
    '#include "../../module/stepper.h"\n#include "../../sd/cardreader.h"',
    '#include "../../module/stepper.h"\n#include "../../module/motion.h"\n#if HAS_LEVELING\n  #include "../../feature/bedlevel/bedlevel.h"\n#endif\n#include "../../sd/cardreader.h"',
    "test cube includes",
)

cube_code = r"""
// --------------------------------------------------------------------------
// Monster8 stand-alone LCD setup cube
// --------------------------------------------------------------------------
// Prints an adjustable calibration cube without a PC or SD G-code file.
// Uses current X/Y, homes Z only, uses the saved probe Z offset, prints two
// priming lines, and allows live +/-0.05mm Z adjustment from the LCD.

enum Monster8TestCubeState : uint8_t {
  M8TC_IDLE,
  M8TC_HOME_Z,
  M8TC_WAIT_HOME,
  M8TC_WAIT_HEAT,
  M8TC_SETUP_G90,
  M8TC_SETUP_M83,
  M8TC_SETUP_E0,
  M8TC_SETUP_FAN,
  M8TC_FIRST_LAYER_Z,
  M8TC_SETUP_G91,
  M8TC_PRIME_LINE1,
  M8TC_PRIME_STEP,
  M8TC_PRIME_LINE2,
  M8TC_PRIME_TO_CUBE,
  M8TC_OUTER_START,
  M8TC_OUTER_EDGE,
  M8TC_INNER_START,
  M8TC_INNER_EDGE,
  M8TC_BACK_ORIGIN,
  M8TC_INFILL_START,
  M8TC_INFILL_LINE,
  M8TC_INFILL_STEP,
  M8TC_INFILL_RETURN,
  M8TC_NEXT_LAYER,
  M8TC_LAYER_Z,
  M8TC_FINISH_LIFT,
  M8TC_FINISH_G90,
  M8TC_FINISH_M82,
  M8TC_FINISH_FAN,
  M8TC_FINISH_SYNC,
  M8TC_WAIT_DONE
};

static Monster8TestCubeState m8tc_state = M8TC_IDLE;
static int16_t m8tc_temp = 230;
static int16_t m8tc_size = 10;       // cube X/Y/Z size in mm
static int16_t m8tc_speed = 25;      // print speed in mm/s
static uint8_t m8tc_nozzle = 2;      // 0=.4mm, 1=.6mm, 2=.8mm

static float m8tc_layer_h, m8tc_line_w, m8tc_e_per_mm,
             m8tc_x, m8tc_y, m8tc_infill_spacing, m8tc_infill_span,
             m8tc_prime_length;
static uint16_t m8tc_layers, m8tc_layer;
static uint8_t m8tc_bottom_layers, m8tc_edge,
               m8tc_infill_index, m8tc_infill_count;
static int8_t m8tc_infill_dir;
static bool m8tc_infill_horizontal;

static bool m8tc_enqueue_xy(const float dx, const float dy, const uint16_t feed) {
  char sx[14], sy[14], cmd[48];
  dtostrf(dx, 1, 3, sx);
  dtostrf(dy, 1, 3, sy);
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 X%s Y%s F%u"), sx, sy, feed);
  return queue.enqueue_one(cmd);
}

static bool m8tc_enqueue_axis_e(const char axis, const float distance, const float e, const uint16_t feed) {
  char sd[14], se[14], cmd[48];
  dtostrf(distance, 1, 3, sd);
  dtostrf(e, 1, 4, se);
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 %c%s E%s F%u"), axis, sd, se, feed);
  return queue.enqueue_one(cmd);
}

static bool m8tc_enqueue_e(const float e, const uint16_t feed) {
  char se[14], cmd[32];
  dtostrf(e, 1, 3, se);
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 E%s F%u"), se, feed);
  return queue.enqueue_one(cmd);
}

static bool m8tc_enqueue_z_relative(const float dz) {
  char sz[14], cmd[32];
  dtostrf(dz, 1, 4, sz);
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%s F300"), sz);
  return queue.enqueue_one(cmd);
}

static bool m8tc_enqueue_z_absolute(const float z) {
  char sz[14], cmd[32];
  dtostrf(z, 1, 4, sz);
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%s F300"), sz);
  return queue.enqueue_one(cmd);
}

static void m8tc_set_profile() {
  float nominal_h;

  switch (m8tc_nozzle) {
    default:
    case 0: // 0.4mm
      nominal_h = 0.2000f;
      m8tc_bottom_layers = 4;
      m8tc_line_w = 0.4500f;
      break;
    case 1: // 0.6mm
      nominal_h = 0.3000f;
      m8tc_bottom_layers = 3;
      m8tc_line_w = 0.6750f;
      break;
    case 2: // 0.8mm
      nominal_h = 0.4000f;
      m8tc_bottom_layers = 2;
      m8tc_line_w = 0.9000f;
      break;
  }

  // Choose a whole number of layers, then slightly adjust layer height so
  // the requested cube height is exact.
  m8tc_layers = uint16_t(float(m8tc_size) / nominal_h + 0.5f);
  if (m8tc_layers < 1) m8tc_layers = 1;
  m8tc_layer_h = float(m8tc_size) / float(m8tc_layers);

  // 1.75mm filament cross-sectional area = ~2.4053mm2.
  m8tc_e_per_mm = (m8tc_layer_h * m8tc_line_w) / 2.4053f;

  // Two priming lines. At least 20mm long, or cube width if larger.
  m8tc_prime_length = m8tc_size > 20 ? float(m8tc_size) : 20.0f;
}

static void m8tc_start() {
  if (m8tc_state != M8TC_IDLE) return;

  m8tc_set_profile();
  m8tc_layer = 0;
  m8tc_x = m8tc_y = 0;
  m8tc_state = M8TC_HOME_Z;

  thermalManager.setTargetHotend(m8tc_temp, 0);
  ui.set_status(F("Test: Home Z / Heat"));
  ui.defer_status_screen();
}

static void m8tc_stop() {
  m8tc_state = M8TC_IDLE;
  queue.inject_P(nullptr);
  queue.clear();
  quickstop_stepper();
  thermalManager.disable_all_heaters();

  // Restore the normal slicer coordinate modes after an interrupted test.
  queue.inject(F("G90\nM82\nM107"));
  ui.set_status(F("Test Cube Stopped"));
  ui.completion_feedback();
  ui.return_to_status();
}

static void m8tc_cycle_nozzle() {
  if (++m8tc_nozzle > 2) m8tc_nozzle = 0;
  ui.refresh(LCDVIEW_CLEAR_CALL_REDRAW);
}

static void m8tc_z_closer() {
  if (m8tc_state == M8TC_IDLE) return;
  queue.inject(F("M290 Z-0.05"));
  ui.set_status(F("Live Z: Closer .05"));
}

static void m8tc_z_farther() {
  if (m8tc_state == M8TC_IDLE) return;
  queue.inject(F("M290 Z0.05"));
  ui.set_status(F("Live Z: Farther .05"));
}

void monster8_test_cube_task() {
  if (m8tc_state == M8TC_IDLE) return;

  const uint16_t print_feed = uint16_t(m8tc_speed) * 60U;

  switch (m8tc_state) {

    case M8TC_HOME_Z:
      if (queue.enqueue_one(F("G28 Z")))
        m8tc_state = M8TC_WAIT_HOME;
      break;

    case M8TC_WAIT_HOME:
      if (!queue.has_commands_queued()) {
        #if HAS_LEVELING
          if (leveling_is_valid()) set_bed_leveling_enabled(true);
        #endif
        m8tc_state = M8TC_WAIT_HEAT;
        ui.set_status(F("Test: Heating nozzle"));
      }
      break;

    case M8TC_WAIT_HEAT:
      if (thermalManager.degHotend(0) >= float(m8tc_temp - 2)) {
        m8tc_state = M8TC_SETUP_G90;
        ui.set_status(F("Test: First layer"));
      }
      break;

    // IMPORTANT: Home Z with the probe can leave the nozzle physically above
    // the bed by the probe offset. Move to the first-layer height in absolute
    // coordinates before switching to relative moves.
    case M8TC_SETUP_G90:
      if (queue.enqueue_one(F("G90"))) m8tc_state = M8TC_SETUP_M83;
      break;

    case M8TC_SETUP_M83:
      if (queue.enqueue_one(F("M83"))) m8tc_state = M8TC_SETUP_E0;
      break;

    case M8TC_SETUP_E0:
      if (queue.enqueue_one(F("G92 E0"))) m8tc_state = M8TC_SETUP_FAN;
      break;

    case M8TC_SETUP_FAN:
      if (queue.enqueue_one(F("M107"))) m8tc_state = M8TC_FIRST_LAYER_Z;
      break;

    case M8TC_FIRST_LAYER_Z:
      if (m8tc_enqueue_z_absolute(m8tc_layer_h))
        m8tc_state = M8TC_SETUP_G91;
      break;

    case M8TC_SETUP_G91:
      if (queue.enqueue_one(F("G91"))) {
        m8tc_state = M8TC_PRIME_LINE1;
        ui.set_status(F("Test: Priming lines"));
      }
      break;

    case M8TC_PRIME_LINE1: {
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

    case M8TC_OUTER_START: {
      const float o = m8tc_line_w * 0.5f;
      if (m8tc_enqueue_xy(o, o, 3000)) {
        m8tc_x = m8tc_y = o;
        m8tc_edge = 0;
        m8tc_state = M8TC_OUTER_EDGE;
      }
    } break;

    case M8TC_OUTER_EDGE: {
      const float side = float(m8tc_size) - m8tc_line_w;
      const bool xaxis = !(m8tc_edge & 1);
      const float distance = (m8tc_edge < 2 ? 1.0f : -1.0f) * side;
      const float e = side * m8tc_e_per_mm;
      if (m8tc_enqueue_axis_e(xaxis ? 'X' : 'Y', distance, e, print_feed)) {
        if (xaxis) m8tc_x += distance; else m8tc_y += distance;
        if (++m8tc_edge >= 4)
          m8tc_state = M8TC_INNER_START;
      }
    } break;

    case M8TC_INNER_START:
      if (m8tc_enqueue_xy(m8tc_line_w, m8tc_line_w, 3000)) {
        m8tc_x += m8tc_line_w;
        m8tc_y += m8tc_line_w;
        m8tc_edge = 0;
        m8tc_state = M8TC_INNER_EDGE;
      }
      break;

    case M8TC_INNER_EDGE: {
      const float side = float(m8tc_size) - 3.0f * m8tc_line_w;
      const bool xaxis = !(m8tc_edge & 1);
      const float distance = (m8tc_edge < 2 ? 1.0f : -1.0f) * side;
      const float e = side * m8tc_e_per_mm;
      if (m8tc_enqueue_axis_e(xaxis ? 'X' : 'Y', distance, e, print_feed)) {
        if (xaxis) m8tc_x += distance; else m8tc_y += distance;
        if (++m8tc_edge >= 4)
          m8tc_state = M8TC_BACK_ORIGIN;
      }
    } break;

    case M8TC_BACK_ORIGIN:
      if (m8tc_enqueue_xy(-m8tc_x, -m8tc_y, 3000)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_INFILL_START;
      }
      break;

    case M8TC_INFILL_START: {
      const bool solid = m8tc_layer < m8tc_bottom_layers
                      || m8tc_layer >= m8tc_layers - m8tc_bottom_layers;
      const float a = 2.5f * m8tc_line_w;
      const float b = float(m8tc_size) - a;

      m8tc_infill_span = b - a;
      if (m8tc_infill_span < m8tc_line_w) m8tc_infill_span = m8tc_line_w;
      m8tc_infill_spacing = solid ? m8tc_line_w : 3.0f * m8tc_line_w;
      m8tc_infill_count = uint8_t(m8tc_infill_span / m8tc_infill_spacing) + 1;
      if (m8tc_infill_count < 1) m8tc_infill_count = 1;
      m8tc_infill_index = 0;
      m8tc_infill_dir = 1;
      m8tc_infill_horizontal = !(m8tc_layer & 1);

      if (m8tc_enqueue_xy(a, a, 3000)) {
        m8tc_x = m8tc_y = a;
        m8tc_state = M8TC_INFILL_LINE;
      }
    } break;

    case M8TC_INFILL_LINE: {
      const char axis = m8tc_infill_horizontal ? 'X' : 'Y';
      const float distance = m8tc_infill_dir * m8tc_infill_span;
      const float e = m8tc_infill_span * m8tc_e_per_mm;
      if (m8tc_enqueue_axis_e(axis, distance, e, print_feed)) {
        if (m8tc_infill_horizontal) m8tc_x += distance;
        else                        m8tc_y += distance;

        if (m8tc_infill_index + 1 < m8tc_infill_count)
          m8tc_state = M8TC_INFILL_STEP;
        else
          m8tc_state = M8TC_INFILL_RETURN;
      }
    } break;

    case M8TC_INFILL_STEP: {
      const float dx = m8tc_infill_horizontal ? 0 : m8tc_infill_spacing;
      const float dy = m8tc_infill_horizontal ? m8tc_infill_spacing : 0;
      if (m8tc_enqueue_xy(dx, dy, 3000)) {
        m8tc_x += dx;
        m8tc_y += dy;
        ++m8tc_infill_index;
        m8tc_infill_dir = -m8tc_infill_dir;
        m8tc_state = M8TC_INFILL_LINE;
      }
    } break;

    case M8TC_INFILL_RETURN:
      if (m8tc_enqueue_xy(-m8tc_x, -m8tc_y, 3000)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_NEXT_LAYER;
      }
      break;

    case M8TC_NEXT_LAYER:
      if (++m8tc_layer < m8tc_layers)
        m8tc_state = M8TC_LAYER_Z;
      else {
        thermalManager.setTargetHotend(0, 0);
        m8tc_state = M8TC_FINISH_LIFT;
      }
      break;

    case M8TC_LAYER_Z:
      if (m8tc_enqueue_z_relative(m8tc_layer_h))
        m8tc_state = M8TC_OUTER_START;
      break;

    case M8TC_FINISH_LIFT:
      if (m8tc_enqueue_z_relative(5.0f)) m8tc_state = M8TC_FINISH_G90;
      break;

    case M8TC_FINISH_G90:
      if (queue.enqueue_one(F("G90"))) m8tc_state = M8TC_FINISH_M82;
      break;

    case M8TC_FINISH_M82:
      if (queue.enqueue_one(F("M82"))) m8tc_state = M8TC_FINISH_FAN;
      break;

    case M8TC_FINISH_FAN:
      if (queue.enqueue_one(F("M107"))) m8tc_state = M8TC_FINISH_SYNC;
      break;

    case M8TC_FINISH_SYNC:
      if (queue.enqueue_one(F("M400"))) m8tc_state = M8TC_WAIT_DONE;
      break;

    case M8TC_WAIT_DONE:
      if (!queue.has_commands_queued()) {
        m8tc_state = M8TC_IDLE;
        ui.set_status(F("Test Cube Done"));
        ui.completion_feedback();
        ui.return_to_status();
      }
      break;

    default:
      m8tc_state = M8TC_IDLE;
      thermalManager.disable_all_heaters();
      break;
  }
}

void menu_test_print() {
  ui.defer_status_screen();

  START_MENU();

  if (m8tc_state == M8TC_IDLE) {
    BACK_ITEM(MSG_MAIN_MENU);
    STATIC_ITEM_F(F("Uses current XY"));
    EDIT_ITEM_F(int3, F("Nozzle Temp C"), &m8tc_temp, 170, 280);
    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, 30);
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);

    if (m8tc_nozzle == 0)
      ACTION_ITEM_F(F("Nozzle: 0.4mm"), m8tc_cycle_nozzle);
    else if (m8tc_nozzle == 1)
      ACTION_ITEM_F(F("Nozzle: 0.6mm"), m8tc_cycle_nozzle);
    else
      ACTION_ITEM_F(F("Nozzle: 0.8mm"), m8tc_cycle_nozzle);

    ACTION_ITEM_F(F("Print Test Cube"), m8tc_start);
  }
  else {
    STATIC_ITEM_F(F("Setup Test Running"));
    ACTION_ITEM_F(F("Z Closer -0.05"), m8tc_z_closer);
    ACTION_ITEM_F(F("Z Farther +0.05"), m8tc_z_farther);
    ACTION_ITEM_F(F("STOP TEST"), m8tc_stop);
  }

  END_MENU();
}
"""

replace_once(
    menu,
    "void menu_main() {\n",
    cube_code + "\nvoid menu_main() {\n",
    "insert setup test cube implementation",
)

replace_once(
    menu,
    "    SUBMENU(MSG_MOTION, menu_motion);\n",
    "    SUBMENU(MSG_MOTION, menu_motion);\n    SUBMENU_F(F(\"Setup Test Print\"), menu_test_print);\n",
    "add setup test print submenu",
)

# Run the small state machine once per normal Marlin loop, before the next
# queued command is dispatched. This keeps the LCD responsive and lets STOP
# or live Z adjustment work without a PC or SD print job.
replace_once(
    core,
    '#include "lcd/marlinui.h"\n',
    '#include "lcd/marlinui.h"\n#if HAS_MARLINUI_MENU\n  extern void monster8_test_cube_task();\n#endif\n',
    "declare setup cube task",
)

core_text = core.read_text()
loop_pos = core_text.find("void loop() {")
if loop_pos < 0:
    raise SystemExit("service setup cube task: loop() not found")
idle_pos = core_text.find("    marlin.idle();", loop_pos)
if idle_pos < 0:
    raise SystemExit("service setup cube task: marlin.idle() not found inside loop()")
idle_end = idle_pos + len("    marlin.idle();")
core_text = (
    core_text[:idle_end]
    + "\n\n    #if HAS_MARLINUI_MENU\n      monster8_test_cube_task();\n    #endif"
    + core_text[idle_end:]
)
core.write_text(core_text)

print("Added adjustable LCD setup cube with absolute first-layer Z, two priming lines, speed/size controls, and live Z adjustment")