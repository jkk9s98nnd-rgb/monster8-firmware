from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Test-print startup safety sequence
# ---------------------------------------------------------------------------
# Required order when START is pressed:
#   1. Lift Z 5mm
#   2. Move to logical X0/Y0
#   3. Home Z at that X/Y location
#   4. Heat / begin the normal print cycle
#
# Keep this sequence in the regular firmware task instead of doing blocking
# movement inside the LCD callback.
replace_once(
    "  M8TC_IDLE,\n  M8TC_HOME_Z,",
    "  M8TC_IDLE,\n"
    "  M8TC_START_RELATIVE,\n"
    "  M8TC_START_WAIT_RELATIVE,\n"
    "  M8TC_START_LIFT,\n"
    "  M8TC_START_WAIT_LIFT,\n"
    "  M8TC_START_ABSOLUTE,\n"
    "  M8TC_START_WAIT_ABSOLUTE,\n"
    "  M8TC_START_PARK,\n"
    "  M8TC_START_WAIT_PARK,\n"
    "  M8TC_HOME_Z,",
    "startup states",
)

old_start = '''static void m8tc_start() {
  if (m8tc_state != M8TC_IDLE) return;

  m8tc_set_profile();
  m8tc_layer = 0;
  m8tc_x = m8tc_y = 0;
  m8tc_prime_done = 0;
  m8tc_state = M8TC_HOME_Z;

  thermalManager.setTargetHotend(m8tc_temp, 0);
  ui.set_status(F("Test: Home Z / Heat"));
  ui.defer_status_screen();
}
'''
new_start = '''static void m8tc_start() {
  if (m8tc_state != M8TC_IDLE) return;

  m8tc_set_profile();
  m8tc_layer = 0;
  m8tc_x = m8tc_y = 0;
  m8tc_prime_done = 0;

  // Do not begin homing or heating until the head has safely lifted and moved
  // to the user's logical X0/Y0 work origin.
  m8tc_state = M8TC_START_RELATIVE;
  ui.set_status(F("Test: Lift then X0 Y0"));
  ui.defer_status_screen();
}
'''
replace_once(old_start, new_start, "test start function")

startup_cases = '''    case M8TC_START_RELATIVE:
      if (queue.enqueue_one(F("G91"))) {
        m8tc_state = M8TC_START_WAIT_RELATIVE;
        ui.set_status(F("Test: Preparing lift"));
      }
      break;

    case M8TC_START_WAIT_RELATIVE:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_START_LIFT;
      break;

    case M8TC_START_LIFT:
      if (m8tc_enqueue_z_relative(5.0f)) {
        m8tc_state = M8TC_START_WAIT_LIFT;
        ui.set_status(F("Test: Lifting Z 5mm"));
      }
      break;

    case M8TC_START_WAIT_LIFT:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_START_ABSOLUTE;
      break;

    case M8TC_START_ABSOLUTE:
      if (queue.enqueue_one(F("G90"))) {
        m8tc_state = M8TC_START_WAIT_ABSOLUTE;
        ui.set_status(F("Test: Lifted / Go X0 Y0"));
      }
      break;

    case M8TC_START_WAIT_ABSOLUTE:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_START_PARK;
      break;

    case M8TC_START_PARK:
      if (m8tc_enqueue_xy(0.0f, 0.0f, 3000)) {
        m8tc_state = M8TC_START_WAIT_PARK;
        ui.set_status(F("Test: Moving X0 Y0"));
      }
      break;

    case M8TC_START_WAIT_PARK:
      if (!queue.has_commands_queued()) {
        thermalManager.setTargetHotend(m8tc_temp, 0);
        m8tc_state = M8TC_HOME_Z;
        ui.set_status(F("Test: X0 Y0 / Home Z"));
      }
      break;

'''
home_case = "    case M8TC_HOME_Z:\n"
if home_case not in s:
    raise SystemExit("home-Z state not found")
s = s.replace(home_case, startup_cases + home_case, 1)

# The previous mapped-cube patch moved to X0/Y0 after Z homing. That is now
# intentionally done BEFORE Z homing, so remove the redundant post-home move.
old_wait_home = '''    case M8TC_WAIT_HOME:
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
'''
new_wait_home = '''    case M8TC_WAIT_HOME:
      if (!queue.has_commands_queued()) {
        #if HAS_LEVELING
          if (leveling_is_valid()) set_bed_leveling_enabled(true);
        #endif
        m8tc_state = M8TC_WAIT_HEAT;
        ui.set_status(F("Test: Heating nozzle"));
      }
      break;
'''
replace_once(old_wait_home, new_wait_home, "post-home X0/Y0 move")

p.write_text(s)
print("Test print now lifts 5mm, moves to X0/Y0, homes Z there, then starts heat/print cycle")
