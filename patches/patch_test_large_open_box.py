from pathlib import Path
import re

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Independent X / Y / height controls.
# The old single Cube Size value forced X=Y=Z and therefore capped the usable
# footprint at the 305mm Z travel. Keep each axis independent so a test can use
# the whole selected 610 x 914 mapped area while height remains Z-safe.
# ---------------------------------------------------------------------------
replace_once(
    'static int16_t m8tc_size = 10;       // cube X/Y/Z size in mm\n',
    'static int16_t m8tc_size_x = 10;     // test width from logical X0\n'
    'static int16_t m8tc_size_y = 10;     // test depth from logical Y0\n'
    'static int16_t m8tc_height = 10;     // test height in Z\n',
    'independent test dimensions',
)

replace_once(
    'static int16_t m8tc_infill_pct = 30; // interior infill, 0..100 percent\n',
    'static int16_t m8tc_infill_pct = 30; // interior infill, 0..100 percent\n'
    'static bool m8tc_bottom_fill = false; // solid bottom skin; OFF = open bottom\n'
    'static bool m8tc_top_fill = false;    // solid top skin; OFF = open top\n',
    'open top bottom controls',
)

replace_once(
    '  m8tc_layers = uint16_t(float(m8tc_size) / nominal_h + 0.5f);\n'
    '  if (m8tc_layers < 1) m8tc_layers = 1;\n'
    '  m8tc_layer_h = float(m8tc_size) / float(m8tc_layers);\n',
    '  m8tc_layers = uint16_t(float(m8tc_height) / nominal_h + 0.5f);\n'
    '  if (m8tc_layers < 1) m8tc_layers = 1;\n'
    '  m8tc_layer_h = float(m8tc_height) / float(m8tc_layers);\n',
    'height profile',
)

# Replace the old square-size helper. X and Y are capped by the selected map;
# height is independently capped by this machine's configured 305mm Z travel.
helper_start = s.find('static int16_t m8tc_max_size() {')
helper_end = s.find('static float m8tc_flow_scale()', helper_start)
if helper_start < 0 or helper_end < 0:
    raise SystemExit('mapped-size helper block not found')
new_helpers = '''static int16_t m8tc_max_x_size() {
  int16_t v = m8_get_mesh_x_mm();
  if (v > 610) v = 610;
  if (v < 5) v = 5;
  return v;
}

static int16_t m8tc_max_y_size() {
  int16_t v = m8_get_mesh_y_mm();
  if (v > 914) v = 914;
  if (v < 5) v = 5;
  return v;
}

static int16_t m8tc_max_height() {
  return 305;
}

'''
s = s[:helper_start] + new_helpers + s[helper_end:]


# ---------------------------------------------------------------------------
# Rectangular perimeter walls. Each edge uses the selected dimension for that
# axis instead of assuming one square side length.
# ---------------------------------------------------------------------------
replace_once(
    '    case M8TC_OUTER_EDGE: {\n'
    '      const float side = float(m8tc_size) - m8tc_line_w;\n'
    '      const bool xaxis = !(m8tc_edge & 1);\n',
    '    case M8TC_OUTER_EDGE: {\n'
    '      const bool xaxis = !(m8tc_edge & 1);\n'
    '      const float side = float(xaxis ? m8tc_size_x : m8tc_size_y) - m8tc_line_w;\n',
    'rectangular outer wall',
)

replace_once(
    '    case M8TC_INNER_EDGE: {\n'
    '      const float side = float(m8tc_size) - 3.0f * m8tc_line_w;\n'
    '      const bool xaxis = !(m8tc_edge & 1);\n',
    '    case M8TC_INNER_EDGE: {\n'
    '      const bool xaxis = !(m8tc_edge & 1);\n'
    '      const float side = float(xaxis ? m8tc_size_x : m8tc_size_y) - 3.0f * m8tc_line_w;\n',
    'rectangular inner wall',
)


# ---------------------------------------------------------------------------
# Rectangular infill and independent top / bottom skins.
# Bottom Fill OFF and Top Fill OFF remove the solid skins completely. Sparse
# infill is still governed by Infill %. Setting Infill to 0 makes a fully hollow
# open box with only the two perimeter walls.
# ---------------------------------------------------------------------------
old_infill = '''    case M8TC_INFILL_START: {
      const bool solid = m8tc_layer < m8tc_bottom_layers
                      || m8tc_layer >= m8tc_layers - m8tc_bottom_layers;
      const float a = 2.5f * m8tc_line_w;
      const float b = float(m8tc_size) - a;

      m8tc_infill_span = b - a;
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
      m8tc_infill_dir = 1;
      m8tc_infill_horizontal = !(m8tc_layer & 1);
'''
new_infill = '''    case M8TC_INFILL_START: {
      const bool solid = (m8tc_bottom_fill && m8tc_layer < m8tc_bottom_layers)
                      || (m8tc_top_fill && m8tc_layer + m8tc_bottom_layers >= m8tc_layers);
      const float a = 2.5f * m8tc_line_w;
      m8tc_infill_horizontal = !(m8tc_layer & 1);

      float line_span = float(m8tc_infill_horizontal ? m8tc_size_x : m8tc_size_y) - 2.0f * a;
      float cross_span = float(m8tc_infill_horizontal ? m8tc_size_y : m8tc_size_x) - 2.0f * a;
      if (line_span < m8tc_line_w) line_span = m8tc_line_w;
      if (cross_span < m8tc_line_w) cross_span = m8tc_line_w;
      m8tc_infill_span = line_span;

      if (!solid && m8tc_infill_pct <= 0) {
        m8tc_infill_count = 0;
        m8tc_state = M8TC_NEXT_LAYER;
        break;
      }

      m8tc_infill_spacing = solid
        ? m8tc_line_w
        : m8tc_line_w * 100.0f / float(m8tc_infill_pct);
      m8tc_infill_count = uint16_t(cross_span / m8tc_infill_spacing) + 1;
      if (m8tc_infill_count < 1) m8tc_infill_count = 1;
      m8tc_infill_index = 0;
      m8tc_infill_dir = 1;
'''
replace_once(old_infill, new_infill, 'rectangular infill and skins')


# ---------------------------------------------------------------------------
# LCD controls. Defaults have both solid skins OFF as requested.
# X and Y can use the full selected map independently; height is independent.
# ---------------------------------------------------------------------------
replace_once(
    '    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, m8tc_max_size());\n',
    '    EDIT_ITEM_F(int3, F("X Size mm"), &m8tc_size_x, 5, m8tc_max_x_size());\n'
    '    EDIT_ITEM_F(int3, F("Y Size mm"), &m8tc_size_y, 5, m8tc_max_y_size());\n'
    '    EDIT_ITEM_F(int3, F("Height mm"), &m8tc_height, 1, m8tc_max_height());\n'
    '    EDIT_ITEM_F(bool, F("Bottom Fill"), &m8tc_bottom_fill);\n'
    '    EDIT_ITEM_F(bool, F("Top Fill"), &m8tc_top_fill);\n',
    'LCD size and skin controls',
)

# Guard against accidentally leaving any use of the old single dimension.
if re.search(r'\bm8tc_size\b', s):
    raise SystemExit('old single m8tc_size reference remains after rectangular conversion')

p.write_text(s)
print('Added full mapped-area X/Y test sizing, independent height, and selectable open top/bottom skins')
