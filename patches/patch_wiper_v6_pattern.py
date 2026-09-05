from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"


def find_function_end(text: str, signature: str) -> int:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Wiper V6: function not found: {signature}")
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f"Wiper V6: opening brace not found: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    raise SystemExit(f"Wiper V6: closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# Monster8 Wiper V6
# User wants more aggressive cleaning using essentially the whole 8.4 x 18.8mm
# rubber wiper. Each Pattern Cycle performs one full-width zig-zag and one
# figure-8. Default is 2 cycles, followed by one straight cleanup sweep.
# Slight overtravel past the rubber edges is intentional per user request.
# Keep proven direct blocking motion and Z3.50 contact height.
# ---------------------------------------------------------------------------
s = g28.read_text()

if 'float m8_wiper_z = 3.50f;' not in s:
    raise SystemExit("Wiper V6: expected Z3.50 default missing")

if 'int16_t m8_wiper_passes = 4;' not in s:
    raise SystemExit("Wiper V6: expected prior pass default 4 missing")
s = s.replace('int16_t m8_wiper_passes = 4;', 'int16_t m8_wiper_passes = 2;', 1)

run_sig = 'static void m8_wiper_run_now(const bool restore_leveling)'
run_start = s.find(run_sig)
run_end = find_function_end(s, run_sig)

new_run = '''static void m8_wiper_run_now(const bool restore_leveling) {\n  const float wz = m8_clamp_z(m8_wiper_z);\n  const int16_t cycles = m8_clamp_passes(m8_wiper_passes);\n  const float wipe_fr = float(m8_clamp_speed(m8_wiper_speed));\n\n  // Intentional full-surface pattern. Physical rubber is approximately\n  // X-34.2..-25.8 and Y-39.4..-20.6. The path slightly overtravels the\n  // edges to wipe all sides of the nozzle and use the entire rubber surface.\n  constexpr float XL = -35.0f, XR = -25.0f;\n  constexpr float YF = -40.0f, YB = -20.0f;\n  constexpr float XC = -30.0f, YC = -30.0f;\n\n  ui.set_status(F("Nozzle Wiping"), 0);\n  TERN_(HAS_LEVELING, set_bed_leveling_enabled(false));\n\n  const float safe_z = current_position.z < M8_WIPER_SAFE_Z ? M8_WIPER_SAFE_Z : current_position.z;\n  if (current_position.z < safe_z) do_blocking_move_to_z(safe_z, 10.0f);\n  do_blocking_move_to_xy(XC, YF, 40.0f);\n  do_blocking_move_to_z(wz, 5.0f);\n\n  // Zig-zags: alternate travel direction each cycle to scrub both ways.\n  for (int16_t c = 0; c < cycles; ++c) {\n    if (!(c & 1)) {\n      do_blocking_move_to_xy(XL, YF, wipe_fr);\n      do_blocking_move_to_xy(XR, -36.0f, wipe_fr);\n      do_blocking_move_to_xy(XL, -32.0f, wipe_fr);\n      do_blocking_move_to_xy(XR, -28.0f, wipe_fr);\n      do_blocking_move_to_xy(XL, -24.0f, wipe_fr);\n      do_blocking_move_to_xy(XR, YB, wipe_fr);\n    }\n    else {\n      do_blocking_move_to_xy(XL, YB, wipe_fr);\n      do_blocking_move_to_xy(XR, -24.0f, wipe_fr);\n      do_blocking_move_to_xy(XL, -28.0f, wipe_fr);\n      do_blocking_move_to_xy(XR, -32.0f, wipe_fr);\n      do_blocking_move_to_xy(XL, -36.0f, wipe_fr);\n      do_blocking_move_to_xy(XR, YF, wipe_fr);\n    }\n  }\n\n  // Figure-8s: two large lobes crossing at the wiper center.\n  for (int16_t c = 0; c < cycles; ++c) {\n    do_blocking_move_to_xy(XC, YC, wipe_fr);\n    do_blocking_move_to_xy(XL, -34.0f, wipe_fr);\n    do_blocking_move_to_xy(XL, -38.0f, wipe_fr);\n    do_blocking_move_to_xy(XC, YF, wipe_fr);\n    do_blocking_move_to_xy(XR, -38.0f, wipe_fr);\n    do_blocking_move_to_xy(XR, -34.0f, wipe_fr);\n    do_blocking_move_to_xy(XC, YC, wipe_fr);\n    do_blocking_move_to_xy(XL, -26.0f, wipe_fr);\n    do_blocking_move_to_xy(XL, -22.0f, wipe_fr);\n    do_blocking_move_to_xy(XC, YB, wipe_fr);\n    do_blocking_move_to_xy(XR, -22.0f, wipe_fr);\n    do_blocking_move_to_xy(XR, -26.0f, wipe_fr);\n    do_blocking_move_to_xy(XC, YC, wipe_fr);\n  }\n\n  // Final straight sweep drags any loosened material fully off the rubber.\n  do_blocking_move_to_xy(XC, YF, wipe_fr);\n  do_blocking_move_to_xy(XC, YB, wipe_fr);\n\n  do_blocking_move_to_z(M8_WIPER_SAFE_Z, 10.0f);\n  do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);\n\n  if (restore_leveling) TERN_(HAS_LEVELING, set_bed_leveling_enabled(true));\n}\n'''

s = s[:run_start] + new_run + s[run_end + 1:]
g28.write_text(s)

s = menu.read_text()
old_label = 'EDIT_ITEM_F(int3, F("Wipe Passes"), &m8_wiper_passes, 1, 8);'
new_label = 'EDIT_ITEM_F(int3, F("Pattern Cycles"), &m8_wiper_passes, 1, 8);'
if old_label not in s:
    raise SystemExit("Wiper V6: Wipe Passes menu item not found")
s = s.replace(old_label, new_label, 1)

old_hint = '  STATIC_ITEM_F(F("Default contact Z3.50"));\n'
new_hint = '  STATIC_ITEM_F(F("Z3.50 / zigzag + figure8"));\n'
if old_hint not in s:
    raise SystemExit("Wiper V6: V5 hint not found")
s = s.replace(old_hint, new_hint, 1)
menu.write_text(s)

# Regression guards.
g28_text = g28.read_text()
menu_text = menu.read_text()
bed_text = bed.read_text()
for required in [
    'float m8_wiper_z = 3.50f;',
    'int16_t m8_wiper_passes = 2;',
    'constexpr float XL = -35.0f, XR = -25.0f;',
    'constexpr float YF = -40.0f, YB = -20.0f;',
    'do_blocking_move_to_xy(XL, -34.0f, wipe_fr);',
    'do_blocking_move_to_xy(XR, -26.0f, wipe_fr);',
    'do_blocking_move_to_xy(XC, YB, wipe_fr);',
    'constexpr int16_t TEST_TEMP = 240;',
    'm8_wiper_run_now(false);',
    'int16_t m8_auto_prime_length = 60;',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper V6 runtime regression: {required}")

for required in [
    'F("Wiper Enabled")',
    'F("Pattern Cycles")',
    'F("Wipe Speed mm/s")',
    'F("Test Hot Wipe")',
    'STATIC_ITEM_F(F("Z3.50 / zigzag + figure8"));',
]:
    if required not in menu_text:
        raise SystemExit(f"Wiper V6 menu regression: {required}")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper V6 bed regression: {required}")

print("Monster8 Wiper V6: Z3.50 default, 2 zigzags + 2 figure-8s + straight cleanup")
