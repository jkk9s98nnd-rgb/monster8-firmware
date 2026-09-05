from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
menu = root / "src/lcd/menu/menu_main.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"

# Monster8 Wiper V5: hardware-tested wipe works; only change the default
# contact height from Z4.00 to the user's preferred Z3.50. Keep all V4 motion,
# menu behavior, auto-prime, mesh, and virtual-XY protections unchanged.

s = g28.read_text()
old = 'float m8_wiper_z = 4.00f;'
new = 'float m8_wiper_z = 3.50f;'
if old not in s:
    raise SystemExit("Wiper V5: expected V4 Z4.00 default not found")
s = s.replace(old, new, 1)
g28.write_text(s)

s = menu.read_text()
old_hint = '  STATIC_ITEM_F(F("Contact calibrated Z4.00"));\n'
new_hint = '  STATIC_ITEM_F(F("Default contact Z3.50"));\n'
if old_hint not in s:
    raise SystemExit("Wiper V5: V4 contact hint not found")
s = s.replace(old_hint, new_hint, 1)
menu.write_text(s)

# Regression guards: V4 direct motion and all known-good printer behavior stay.
g28_text = g28.read_text()
menu_text = menu.read_text()
bed_text = bed.read_text()

for required in [
    'float m8_wiper_z = 3.50f;',
    'do_blocking_move_to_z(target_z, 5.0f);',
    'do_blocking_move_to_xy(-30.0f, -30.0f, 40.0f);',
    'do_blocking_move_to_xy(M8_WIPER_X, M8_WIPER_Y_START, 40.0f);',
    'm8_wiper_run_now(false);',
    'constexpr int16_t TEST_TEMP = 240;',
    'int16_t m8_auto_prime_length = 60;',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper V5 runtime regression: {required}")

for required in [
    'F("Wiper Enabled")',
    'F("Go to Wiper Z")',
    'F("Z Down 0.05")',
    'F("Z Up 0.05")',
    'F("Test Hot Wipe")',
    'STATIC_ITEM_F(F("Default contact Z3.50"));',
]:
    if required not in menu_text:
        raise SystemExit(f"Wiper V5 menu regression: {required}")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper V5 bed regression: {required}")

print("Monster8 Wiper V5: default wiper contact changed to Z3.50 only")
