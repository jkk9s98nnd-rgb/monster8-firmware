from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
main = root / "src/lcd/menu/menu_main.cpp"

# ---------------------------------------------------------------------------
# Bed Level Setup
# IMPORTANT: Keep the known-good mesh X/Y variables private (static).
# The cube reads them through tiny getter functions instead of changing their
# linkage. This avoids touching the working bed-level state itself.
# ---------------------------------------------------------------------------
text = bed.read_text()

old = """static int16_t m8_mesh_x_mm = 100;
static int16_t m8_mesh_y_mm = 100;

static void m8_run_sized_mesh"""
new = """static int16_t m8_mesh_x_mm = 100;
static int16_t m8_mesh_y_mm = 100;

int16_t m8_get_mesh_x_mm() { return m8_mesh_x_mm; }
int16_t m8_get_mesh_y_mm() { return m8_mesh_y_mm; }

static void m8_run_sized_mesh"""
if old not in text:
    raise SystemExit("private mesh dimension block not found")
text = text.replace(old, new, 1)

# Let Mesh Safe Z go lower than 6 mm while keeping the 10 mm default.
old = 'EDIT_ITEM_F(int3, F("Mesh Safe Z mm"), &m8_mesh_safe_z, 6, 20);'
new = 'EDIT_ITEM_F(int3, F("Mesh Safe Z mm"), &m8_mesh_safe_z, 2, 20);'
if old not in text:
    raise SystemExit("Mesh Safe Z menu range not found")
text = text.replace(old, new, 1)
bed.write_text(text)

# ---------------------------------------------------------------------------
# Test-print upgrades.
# ---------------------------------------------------------------------------
text = main.read_text()

# Read the selected map dimensions through getters. Do NOT export or alter the
# bed-level variables themselves.
include_anchor = '#include "../../module/motion.h"\n'
if include_anchor not in text:
    raise SystemExit("menu_main motion include not found")
text = text.replace(
    include_anchor,
    include_anchor + '\nextern int16_t m8_get_mesh_x_mm();\nextern int16_t m8_get_mesh_y_mm();\n',
    1,
)

# Add infill percentage and widen infill counters for large mapped areas.
old = """static int16_t m8tc_flow = 100;      // live cube extrusion percentage
static int16_t m8tc_prime_lines = 2; // 1..3 priming lines
"""
new = """static int16_t m8tc_flow = 100;      // live cube extrusion percentage
static int16_t m8tc_infill_pct = 30; // interior infill, 0..100 percent
static int16_t m8tc_prime_lines = 2; // 0..3 priming lines
"""
if old not in text:
    raise SystemExit("test-print flow variable block not found")
text = text.replace(old, new, 1)

old = """static uint8_t m8tc_bottom_layers, m8tc_edge,
               m8tc_infill_index, m8tc_infill_count, m8tc_prime_done;
"""
new = """static uint8_t m8tc_bottom_layers, m8tc_edge, m8tc_prime_done;
static uint16_t m8tc_infill_index, m8tc_infill_count;
"""
if old not in text:
    raise SystemExit("test-print infill counter block not found")
text = text.replace(old, new, 1)

# Largest square test is the smaller mapped X/Y dimension, additionally
# limited by the machine's 305 mm Z travel because this remains a cube.
anchor = "static float m8tc_flow_scale() { return float(m8tc_flow) * 0.01f; }\n"
helper = """static int16_t m8tc_max_size() {
  const int16_t mx = m8_get_mesh_x_mm(), my = m8_get_mesh_y_mm();
  int16_t v = mx < my ? mx : my;
  if (v > 305) v = 305;
  if (v < 5) v = 5;
  return v;
}

"""
if anchor not in text:
    raise SystemExit("test-print helper insertion point not found")
text = text.replace(anchor, helper + anchor, 1)

# After Z homing, raise first and move to the manually-set X0/Y0. This means
# the test no longer starts wherever the carriage happened to be sitting.
old = """    case M8TC_WAIT_HOME:
      if (!queue.has_commands_queued()) {
        #if HAS_LEVELING
          if (leveling_is_valid()) set_bed_leveling_enabled(true);
        #endif
        m8tc_state = M8TC_WAIT_HEAT;
        ui.set_status(F("Test: Heating nozzle"));
      }
      break;
"""
new = """    case M8TC_WAIT_HOME:
      if (!queue.has_commands_queued()) {
        #if HAS_LEVELING
          if (leveling_is_valid()) set_bed_leveling_enabled(true);
        #endif
        // Establish the print origin from the XY zero set in Bed Level Setup.
        // Lift before the XY move so a low nozzle can't skim the bed.
        queue.inject(F("G90\\nG1 Z5 F600\\nG1 X0 Y0 F3000"));
        m8tc_state = M8TC_WAIT_HEAT;
        ui.set_status(F("Test: Move X0 Y0 / Heat"));
      }
      break;
"""
if old not in text:
    raise SystemExit("test-print post-home block not found")
text = text.replace(old, new, 1)

# Do not start first-layer moves until the X0/Y0 positioning commands finish.
old = """    case M8TC_WAIT_HEAT:
      if (thermalManager.degHotend(0) >= float(m8tc_temp - 2)) {
        m8tc_state = M8TC_SETUP_G90;
        ui.set_status(F("Test: First layer"));
      }
      break;
"""
new = """    case M8TC_WAIT_HEAT:
      if (!queue.has_commands_queued() && thermalManager.degHotend(0) >= float(m8tc_temp - 2)) {
        m8tc_state = M8TC_SETUP_G90;
        ui.set_status(F("Test: First layer"));
      }
      break;
"""
if old not in text:
    raise SystemExit("test-print heat wait block not found")
text = text.replace(old, new, 1)

# Prime lines may be disabled (0) for a test that fills the whole mapped area.
old = """    case M8TC_SETUP_G91:
      if (queue.enqueue_one(F("G91"))) {
        m8tc_state = M8TC_PRIME_LINE1;
        ui.set_status(F("Test: Priming lines"));
      }
      break;
"""
new = """    case M8TC_SETUP_G91:
      if (queue.enqueue_one(F("G91"))) {
        if (m8tc_prime_lines > 0) {
          m8tc_state = M8TC_PRIME_LINE1;
          ui.set_status(F("Test: Priming lines"));
        }
        else {
          m8tc_state = M8TC_OUTER_START;
          ui.set_status(F("Printing Test Cube"));
        }
      }
      break;
"""
if old not in text:
    raise SystemExit("test-print G91/prime block not found")
text = text.replace(old, new, 1)

# Return from priming to the actual X0/Y0 cube origin. Lift first so the nozzle
# can't scrape across the fresh prime lines.
old = """    case M8TC_PRIME_TO_CUBE:
      // Leave a generous gap between the priming lines and the test cube so
      // the purge is easy to see and cannot merge into the first layer.
      if (m8tc_enqueue_xy(0, 18.0f, 1800)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_OUTER_START;
        ui.set_status(F("Printing Test Cube"));
      }
      break;
"""
new = """    case M8TC_PRIME_TO_CUBE: {
      const float rx = (m8tc_prime_done & 1) ? -m8tc_prime_length : 0.0f;
      const float ry = -2.0f * float(m8tc_prime_done > 0 ? m8tc_prime_done - 1 : 0);
      char sx[14], sy[14], cmd[120];
      dtostrf(rx, 1, 3, sx);
      dtostrf(ry, 1, 3, sy);
      snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z2 F600\\nG1 X%s Y%s F3000\\nG1 Z-2 F600"), sx, sy);
      queue.inject(cmd);
      m8tc_x = m8tc_y = 0;
      m8tc_state = M8TC_OUTER_START;
      ui.set_status(F("Printing Test Cube"));
    } break;
"""
if old not in text:
    raise SystemExit("test-print prime-to-cube block not found")
text = text.replace(old, new, 1)

# Interior infill is now user-selectable. Top and bottom layers remain solid.
old = """      m8tc_infill_span = b - a;
      if (m8tc_infill_span < m8tc_line_w) m8tc_infill_span = m8tc_line_w;
      m8tc_infill_spacing = solid ? m8tc_line_w : 3.0f * m8tc_line_w;
      m8tc_infill_count = uint8_t(m8tc_infill_span / m8tc_infill_spacing) + 1;
      if (m8tc_infill_count < 1) m8tc_infill_count = 1;
      m8tc_infill_index = 0;
"""
new = """      m8tc_infill_span = b - a;
      if (m8tc_infill_span < m8tc_line_w) m8tc_infill_span = m8tc_line_w;

      if (!solid && m8tc_infill_pct <= 0) {
        m8tc_infill_count = 0;
        m8tc_state = M8TC_NEXT_LAYER;
        break;
      }

      m8tc_infill_spacing = solid
        ? m8tc_line_w
        : m8tc_line_w * 100.0f / float(m8tc_infill_pct);
      m8tc_infill_count = uint16_t(m8tc_infill_span / m8tc_infill_spacing) + 1;
      if (m8tc_infill_count < 1) m8tc_infill_count = 1;
      m8tc_infill_index = 0;
"""
if old not in text:
    raise SystemExit("test-print infill spacing block not found")
text = text.replace(old, new, 1)

# Dynamic mapped-area size limit, infill control, and 0..3 prime lines.
old = """    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, 30);
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);
    EDIT_ITEM_F(int3, F("Flow %"), &m8tc_flow, 50, 150);
    EDIT_ITEM_F(int3, F("Prime Lines"), &m8tc_prime_lines, 1, 3);
"""
new = """    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, m8tc_max_size());
    EDIT_ITEM_F(int3, F("Infill %"), &m8tc_infill_pct, 0, 100);
    EDIT_ITEM_F(int3, F("Speed mm/s"), &m8tc_speed, 5, 100);
    EDIT_ITEM_F(int3, F("Flow %"), &m8tc_flow, 50, 150);
    EDIT_ITEM_F(int3, F("Prime Lines"), &m8tc_prime_lines, 0, 3);
"""
if old not in text:
    raise SystemExit("test-print LCD settings block not found")
text = text.replace(old, new, 1)

# STOP: hard-stop the active move, immediately perform a blocking Z lift, then
# park X/Y. The lift is no longer merely queued behind other processing.
old = """static void m8tc_stop() {
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
new = """static void m8tc_stop() {
  m8tc_state = M8TC_IDLE;
  queue.inject_P(nullptr);
  queue.clear();
  quickstop_stepper();
  thermalManager.disable_all_heaters();

  // Lift NOW, before any park command is queued. quickstop_stepper() has
  // already re-synchronized current_position from the physical steppers.
  const float lift_to = _MIN(current_position.z + 5.0f, float(Z_MAX_POS));
  do_blocking_move_to_z(lift_to, 10.0f);

  // Only after the physical Z lift completes do we park at the work origin.
  queue.inject(F("G90\\nG1 X0 Y0 F3000\\nM82\\nM107"));
  ui.set_status(F("Stopped: Lift / Park"));
  ui.completion_feedback();
  ui.return_to_status();
}
"""
if old not in text:
    raise SystemExit("test-print stop routine not found")
text = text.replace(old, new, 1)

main.write_text(text)
print("Added mapped-area cube features without changing private bed-level mesh state")
