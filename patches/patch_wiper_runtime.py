from pathlib import Path

root = Path("MarlinSource/Marlin")
feature_h = root / "src/feature/m8_wiper.h"
feature_cpp = root / "src/feature/m8_wiper.cpp"
main = root / "src/lcd/menu/menu_main.cpp"
g28 = root / "src/gcode/calibrate/G28.cpp"
m109 = root / "src/gcode/temp/M104_M109.cpp"
m1001 = root / "src/gcode/sd/M1001.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
adv = root / "Configuration_adv.h"


def find_function_end(text: str, signature: str) -> int:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f"opening brace not found: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    raise SystemExit(f"closing brace not found: {signature}")


# ---------------------------------------------------------------------------
# Dedicated Monster8 wiper feature. Settings are RAM-only on purpose so this
# feature cannot change Marlin's EEPROM layout and disturb the proven mesh.
# Defaults keep automatic wiping OFF and the contact Z safely above the 4.8mm
# rubber wiper until calibration is completed at the printer.
# ---------------------------------------------------------------------------
feature_h.write_text(r'''#pragma once

#include "../inc/MarlinConfigPre.h"

extern bool m8_wiper_enabled;
extern bool m8_wiper_before_enabled;
extern bool m8_wiper_after_enabled;
extern float m8_wiper_z;
extern int16_t m8_wiper_passes;
extern int16_t m8_wiper_speed;

void m8_wiper_note_print_temperature(const int16_t temp);
void m8_wiper_before_print();
bool m8_wiper_after_print();

void m8_wiper_queue_align_center();
void m8_wiper_queue_return_zero();
void m8_wiper_queue_go_z();
void m8_wiper_queue_z_down();
void m8_wiper_queue_z_up();
void m8_wiper_queue_test();
''')

feature_cpp.write_text(r'''#include "../inc/MarlinConfig.h"
#include "m8_wiper.h"

#include "../gcode/gcode.h"
#include "../gcode/queue.h"
#include "../module/planner.h"
#include "../module/temperature.h"
#include "../lcd/marlinui.h"

// Physical layout agreed for the AD5X rubber wiper:
// center X-30 / Y-30, 8.4mm along X, 18.8mm along Y.
static constexpr float M8_WIPER_X = -30.0f;
static constexpr float M8_WIPER_Y_START = -39.0f;
static constexpr float M8_WIPER_Y_END = -21.0f;
static constexpr float M8_WIPER_SAFE_Z = 10.0f;
static constexpr int16_t M8_WIPER_MIN_TEMP = 170;

bool m8_wiper_enabled = false;          // Deliberately OFF until contact Z is calibrated.
bool m8_wiper_before_enabled = true;
bool m8_wiper_after_enabled = true;
float m8_wiper_z = 6.00f;               // Safe starting value; rubber top is about Z4.8.
int16_t m8_wiper_passes = 4;            // One pass = one Y traverse across the rubber.
int16_t m8_wiper_speed = 15;            // mm/s
static int16_t m8_wiper_last_print_temp = 0;

static float m8_clamp_z(const float z) {
  return z < 4.00f ? 4.00f : (z > 8.00f ? 8.00f : z);
}

static int16_t m8_clamp_passes(const int16_t p) {
  return p < 1 ? 1 : (p > 8 ? 8 : p);
}

static int16_t m8_clamp_speed(const int16_t s) {
  return s < 5 ? 5 : (s > 30 ? 30 : s);
}

void m8_wiper_note_print_temperature(const int16_t temp) {
  if (temp >= M8_WIPER_MIN_TEMP)
    m8_wiper_last_print_temp = temp;
}

// Synchronous version used only from G-code handlers (M109 / M1001).
// It disables mesh compensation before moving outside the mapped bed, raises
// and parks at X0/Y0 first, performs alternating Y wipes, lifts, returns X0/Y0,
// and optionally restores the saved mesh for the print that is about to start.
static void m8_wiper_run_now(const bool restore_leveling) {
  const float wz = m8_clamp_z(m8_wiper_z);
  const int16_t passes = m8_clamp_passes(m8_wiper_passes);
  const int16_t wipe_f = m8_clamp_speed(m8_wiper_speed) * 60;

  char cmd[512];
  int used = snprintf_P(
    cmd, sizeof(cmd),
    PSTR("M420 S0\nG27\nG90\nG1 X-30 Y-39 F2400\nG1 Z%.2f F300"),
    double(wz)
  );

  for (int16_t i = 0; i < passes && used > 0 && used < int(sizeof(cmd)); ++i) {
    const int y = (i & 1) ? -39 : -21;
    used += snprintf_P(cmd + used, sizeof(cmd) - used, PSTR("\nG1 Y%i F%i"), y, int(wipe_f));
  }

  if (used > 0 && used < int(sizeof(cmd)))
    used += snprintf_P(cmd + used, sizeof(cmd) - used,
                       PSTR("\nG1 Z10 F600\nG1 X0 Y0 F2400%s"),
                       restore_leveling ? "\nM420 S1" : "");

  if (used <= 0 || used >= int(sizeof(cmd))) {
    ui.set_status(F("Wiper command too long"), 0);
    return;
  }

  ui.set_status(F("Nozzle Wiping"), 0);
  gcode.process_subcommands_now(cmd);
}

void m8_wiper_before_print() {
  if (!m8_wiper_enabled || !m8_wiper_before_enabled) return;
  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) {
    ui.set_status(F("Wiper: nozzle too cold"), 0);
    return;
  }
  m8_wiper_run_now(true);
}

bool m8_wiper_after_print() {
  if (!m8_wiper_enabled || !m8_wiper_after_enabled) return false;
  if (m8_wiper_last_print_temp < M8_WIPER_MIN_TEMP) return false;

  // Orca currently turns the hotend off near the end of its file. Re-assert
  // the last real print temperature and wait before wiping so PETG ooze is soft.
  thermalManager.setTargetHotend(m8_wiper_last_print_temp, 0);
  ui.set_status(F("Heating for final wipe"), 0);
  (void)thermalManager.wait_for_hotend(0, false);

  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) return false;

  m8_wiper_run_now(false);
  thermalManager.setTargetHotend(0, 0);
  ui.set_status(F("Print Done - Wiped"), 0);
  return true; // Already lifted and parked at X0/Y0; skip the extra completion G27.
}

// ---------------------------------------------------------------------------
// LCD calibration helpers. These are called from UI callbacks, not G-code
// handlers, so enqueue_one_now is safe and avoids the 64-byte queue.inject
// truncation limit. Every contact move first performs the proven safe G27 park.
// ---------------------------------------------------------------------------
static void m8_queue_dynamic_z() {
  char cmd[32];
  snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z%.2f F300"), double(m8_clamp_z(m8_wiper_z)));
  queue.enqueue_one_now(cmd);
}

void m8_wiper_queue_align_center() {
  queue.enqueue_one_now(F("M420 S0"));
  queue.enqueue_one_now(F("G27"));
  queue.enqueue_one_now(F("G90"));
  queue.enqueue_one_now(F("G1 X-30 Y-30 F2400"));
  queue.enqueue_one_now(F("G1 Z10 F600"));
  ui.set_status(F("Center wiper under nozzle"), 0);
}

void m8_wiper_queue_return_zero() {
  queue.enqueue_one_now(F("M420 S0"));
  queue.enqueue_one_now(F("G27"));
  ui.set_status(F("Wiper setup parked"), 0);
}

void m8_wiper_queue_go_z() {
  m8_wiper_z = m8_clamp_z(m8_wiper_z);
  queue.enqueue_one_now(F("M420 S0"));
  queue.enqueue_one_now(F("G27"));
  queue.enqueue_one_now(F("G90"));
  queue.enqueue_one_now(F("G1 X-30 Y-30 F2400"));
  m8_queue_dynamic_z();
  ui.set_status(F("Check wiper contact"), 0);
}

void m8_wiper_queue_z_down() {
  m8_wiper_z = m8_clamp_z(m8_wiper_z - 0.05f);
  m8_wiper_queue_go_z();
}

void m8_wiper_queue_z_up() {
  m8_wiper_z = m8_clamp_z(m8_wiper_z + 0.05f);
  m8_wiper_queue_go_z();
}

void m8_wiper_queue_test() {
  if (thermalManager.degHotend(0) < M8_WIPER_MIN_TEMP) {
    ui.set_status(F("Heat nozzle above 170C"), 0);
    return;
  }

  const int16_t passes = m8_clamp_passes(m8_wiper_passes);
  const int16_t wipe_f = m8_clamp_speed(m8_wiper_speed) * 60;
  char cmd[32];

  queue.enqueue_one_now(F("M420 S0"));
  queue.enqueue_one_now(F("G27"));
  queue.enqueue_one_now(F("G90"));
  queue.enqueue_one_now(F("G1 X-30 Y-39 F2400"));
  m8_queue_dynamic_z();

  for (int16_t i = 0; i < passes; ++i) {
    const int y = (i & 1) ? -39 : -21;
    snprintf_P(cmd, sizeof(cmd), PSTR("G1 Y%i F%i"), y, int(wipe_f));
    queue.enqueue_one_now(cmd);
  }

  queue.enqueue_one_now(F("G1 Z10 F600"));
  queue.enqueue_one_now(F("G1 X0 Y0 F2400"));
  ui.set_status(F("Test wipe complete"), 0);
}
''')


# ---------------------------------------------------------------------------
# Replace the mounting-only Wiper Setup helper with the full calibration menu.
# ---------------------------------------------------------------------------
s = main.read_text()
inc_anchor = '#include "../../module/stepper.h"\n'
if inc_anchor not in s:
    raise SystemExit("Wiper runtime: menu include anchor missing")
if '#include "../../feature/m8_wiper.h"' not in s:
    s = s.replace(inc_anchor, inc_anchor + '#include "../../feature/m8_wiper.h"\n', 1)

start = s.find('static void m8_wiper_align_center()')
if start < 0:
    raise SystemExit("Wiper runtime requires alignment wizard first")
setup_end = find_function_end(s, 'static void m8_wiper_setup_menu()')
new_helpers = r'''static void m8_wiper_align_center() { m8_wiper_queue_align_center(); ui.return_to_status(); }
static void m8_wiper_return_zero() { m8_wiper_queue_return_zero(); ui.return_to_status(); }
static void m8_wiper_go_contact() { m8_wiper_queue_go_z(); ui.return_to_status(); }
static void m8_wiper_z_down() { m8_wiper_queue_z_down(); ui.return_to_status(); }
static void m8_wiper_z_up() { m8_wiper_queue_z_up(); ui.return_to_status(); }
static void m8_wiper_test_hot() { m8_wiper_queue_test(); ui.return_to_status(); }

static void m8_wiper_setup_menu() {
  START_MENU();
  BACK_ITEM(MSG_MAIN_MENU);
  EDIT_ITEM_F(bool, F("Wiper Enabled"), &m8_wiper_enabled);
  EDIT_ITEM_F(bool, F("Wipe Before Print"), &m8_wiper_before_enabled);
  EDIT_ITEM_F(bool, F("Wipe After Print"), &m8_wiper_after_enabled);
  EDIT_ITEM_F(float42_52, F("Wiper Z mm"), &m8_wiper_z, 4.00f, 8.00f);
  EDIT_ITEM_F(int3, F("Wipe Passes"), &m8_wiper_passes, 1, 8);
  EDIT_ITEM_F(int3, F("Wipe Speed mm/s"), &m8_wiper_speed, 5, 30);
  ACTION_ITEM_F(F("Align Wiper Center"), m8_wiper_align_center);
  ACTION_ITEM_F(F("Go to Wiper Z"), m8_wiper_go_contact);
  ACTION_ITEM_F(F("Z Down 0.05"), m8_wiper_z_down);
  ACTION_ITEM_F(F("Z Up 0.05"), m8_wiper_z_up);
  ACTION_ITEM_F(F("Test Hot Wipe"), m8_wiper_test_hot);
  ACTION_ITEM_F(F("Return XY Zero"), m8_wiper_return_zero);
  STATIC_ITEM_F(F("Center X-30 Y-30"));
  STATIC_ITEM_F(F("Sweep Y-39 to Y-21"));
  END_MENU();
}'''
s = s[:start] + new_helpers + s[setup_end + 1:]
main.write_text(s)


# ---------------------------------------------------------------------------
# External-print handshake: wipe after the nozzle has reached temperature and
# before the auto-prime lines. Wiping remains independent of Auto Prime ON/OFF.
# ---------------------------------------------------------------------------
s = g28.read_text()
inc_anchor = '#include "../../module/temperature.h"\n'
if inc_anchor not in s:
    raise SystemExit("Wiper runtime: G28 temperature include missing")
if '#include "../../feature/m8_wiper.h"' not in s:
    s = s.replace(inc_anchor, inc_anchor + '#include "../../feature/m8_wiper.h"\n', 1)

old_guard = '''  if (!m8_auto_prime_lines || !m8_ignore_xy_home\n      || !m8_auto_prime_home_seen || !m8_auto_prime_heat_seen\n      || m8_auto_prime_done)\n    return;\n\n  // Never extrude unless the nozzle is actually hot enough.\n  if (thermalManager.degHotend(0) < EXTRUDE_MINTEMP)\n    return;\n\n  // Clamp editable LCD values to the reserved safe prime strip.\n'''
new_guard = '''  if (!m8_ignore_xy_home\n      || !m8_auto_prime_home_seen || !m8_auto_prime_heat_seen\n      || m8_auto_prime_done)\n    return;\n\n  // Both the wiper and prime sequence are only allowed after M109 has reached\n  // a real extrusion temperature. Run the optional hot wipe FIRST.\n  if (thermalManager.degHotend(0) < EXTRUDE_MINTEMP)\n    return;\n\n  m8_wiper_before_print();\n\n  // Wiping is independent of prime-line selection. If prime is disabled, mark\n  // this print handshake complete so the wiper cannot run twice.\n  if (!m8_auto_prime_lines) {\n    m8_auto_prime_done = true;\n    return;\n  }\n\n  // Clamp editable LCD values to the reserved safe prime strip.\n'''
if old_guard not in s:
    raise SystemExit("Wiper runtime: auto-prime handshake guard not found")
s = s.replace(old_guard, new_guard, 1)
g28.write_text(s)


# ---------------------------------------------------------------------------
# Remember the last non-cold hotend target. This survives Orca's M104 S0 at the
# end of the file (RAM variable is not overwritten by cold targets) so M1001 can
# re-assert the print temperature for a proper hot final wipe.
# ---------------------------------------------------------------------------
s = m109.read_text()
inc_anchor = '#include "../../MarlinCore.h" // for startOrResumeJob, etc.\n'
if inc_anchor not in s:
    raise SystemExit("Wiper runtime: M104/M109 include anchor missing")
if '#include "../../feature/m8_wiper.h"' not in s:
    s = s.replace(inc_anchor, inc_anchor + '#include "../../feature/m8_wiper.h"\n', 1)

set_anchor = '    thermalManager.setTargetHotend(temp, target_extruder);\n'
if set_anchor not in s:
    raise SystemExit("Wiper runtime: setTargetHotend anchor missing")
if 'm8_wiper_note_print_temperature' not in s:
    s = s.replace(
        set_anchor,
        set_anchor + '    if (target_extruder == 0 && temp >= EXTRUDE_MINTEMP)\n      m8_wiper_note_print_temperature(int16_t(temp));\n',
        1,
    )
m109.write_text(s)


# ---------------------------------------------------------------------------
# Normal SD completion: if final hot wiping is enabled, the wiper function
# reheats to the remembered print target, wipes, turns the heater off, lifts and
# parks X0/Y0. Skip the normal G27 only in that case to avoid a duplicate lift.
# ---------------------------------------------------------------------------
s = m1001.read_text()
inc_anchor = '#include "../../module/temperature.h"\n'
if inc_anchor not in s:
    raise SystemExit("Wiper runtime: M1001 include anchor missing")
if '#include "../../feature/m8_wiper.h"' not in s:
    s = s.replace(inc_anchor, inc_anchor + '#include "../../feature/m8_wiper.h"\n', 1)

release_old = '''  // Inject SD_FINISHED_RELEASECOMMAND, if any\n  #ifdef SD_FINISHED_RELEASECOMMAND\n    process_subcommands_now(F(SD_FINISHED_RELEASECOMMAND));\n  #endif\n'''
release_new = '''  // Monster8 optional hot final wipe. It returns true only when it already\n  // lifted and parked at X0/Y0, so avoid a second G27 lift in that case.\n  const bool m8_wiper_parked = m8_wiper_after_print();\n\n  // Inject SD_FINISHED_RELEASECOMMAND, if any\n  #ifdef SD_FINISHED_RELEASECOMMAND\n    if (!m8_wiper_parked) process_subcommands_now(F(SD_FINISHED_RELEASECOMMAND));\n  #endif\n'''
if release_old not in s:
    raise SystemExit("Wiper runtime: M1001 completion hook missing")
s = s.replace(release_old, release_new, 1)
m1001.write_text(s)


# ---------------------------------------------------------------------------
# Regression guards. This build must retain all proven Monster8 behavior.
# ---------------------------------------------------------------------------
main_text = main.read_text()
g28_text = g28.read_text()
m109_text = m109.read_text()
m1001_text = m1001.read_text()
bed_text = bed.read_text()
adv_text = adv.read_text()

for required in [
    'F("Wiper Enabled")',
    'F("Wiper Z mm")',
    'F("Z Down 0.05")',
    'F("Test Hot Wipe")',
    'SUBMENU_F(F("Wiper Setup"), m8_wiper_setup_menu);',
]:
    if required not in main_text:
        raise SystemExit(f"Wiper menu regression guard failed: {required}")

for required in [
    'm8_wiper_before_print();',
    'int16_t m8_auto_prime_length = 60;',
    'G1 X10 Y10 F2400',
]:
    if required not in g28_text:
        raise SystemExit(f"Wiper/prime integration guard failed: {required}")

if 'm8_wiper_note_print_temperature' not in m109_text:
    raise SystemExit("Wiper print-temperature memory hook missing")
if 'const bool m8_wiper_parked = m8_wiper_after_print();' not in m1001_text:
    raise SystemExit("Wiper SD-completion hook missing")

for required in [
    'const int16_t map_left  = 10,',
    'map_front = 10,',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'GCODES_ITEM_F(F("Go to XY Zero"), F("G90\\nG1 X0 Y0 F3000"));',
]:
    if required not in bed_text:
        raise SystemExit(f"Wiper runtime refuses build: bed/XY-zero regression: {required}")

for required in [
    '#define SD_FINISHED_STEPPERRELEASE false',
    '#define SD_FINISHED_RELEASECOMMAND "G27"',
    '#define EVENT_GCODE_SD_ABORT "G27"',
]:
    if required not in adv_text:
        raise SystemExit(f"Wiper runtime refuses build: pause/park regression: {required}")

if 'EVENT_GCODE_SD_ABORT "G28XY"' in adv_text:
    raise SystemExit("Wiper runtime refuses build: unsafe G28XY abort returned")

print("Added Monster8 Wiper Calibration + hot before/after print wiping; automatic wipe defaults OFF until calibrated")
