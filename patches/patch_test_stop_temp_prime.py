from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) STOP TEST: never block inside the LCD callback.
# ---------------------------------------------------------------------------
# The previous build called do_blocking_move_to_z() directly from m8tc_stop().
# On the Mini12864 that can make the UI appear locked while the callback owns
# the menu update. Instead, cancel immediately and let the regular cube task
# perform a staged lift and park through Marlin's command queue.
replace_once(
    "  M8TC_WAIT_DONE\n};",
    "  M8TC_WAIT_DONE,\n"
    "  M8TC_ABORT_RELATIVE,\n"
    "  M8TC_ABORT_WAIT_RELATIVE,\n"
    "  M8TC_ABORT_LIFT,\n"
    "  M8TC_ABORT_WAIT_LIFT,\n"
    "  M8TC_ABORT_ABSOLUTE,\n"
    "  M8TC_ABORT_WAIT_ABSOLUTE,\n"
    "  M8TC_ABORT_PARK,\n"
    "  M8TC_ABORT_WAIT_PARK\n"
    "};",
    "abort states",
)

stop_start = s.find("static void m8tc_stop() {")
stop_end_anchor = "\n\nstatic void m8tc_cycle_nozzle()"
stop_end = s.find(stop_end_anchor, stop_start)
if stop_start < 0 or stop_end < 0:
    raise SystemExit("m8tc_stop function not found")

new_stop = '''static void m8tc_stop() {
  if (m8tc_state == M8TC_IDLE) return;

  // Cancel the active test immediately. Do not perform a blocking move here;
  // this function runs from the LCD menu callback.
  queue.inject_P(nullptr);
  queue.clear();
  quickstop_stepper();
  thermalManager.disable_all_heaters();

  // The normal firmware loop performs lift -> absolute mode -> park in stages.
  m8tc_state = M8TC_ABORT_RELATIVE;
  ui.set_status(F("STOP: Cancel / Lift"));
  ui.refresh(LCDVIEW_CLEAR_CALL_REDRAW);
}
'''
s = s[:stop_start] + new_stop + s[stop_end:]

abort_cases = '''    case M8TC_ABORT_RELATIVE:
      if (queue.enqueue_one(F("G91"))) {
        m8tc_state = M8TC_ABORT_WAIT_RELATIVE;
        ui.set_status(F("STOP: Preparing lift"));
      }
      break;

    case M8TC_ABORT_WAIT_RELATIVE:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_ABORT_LIFT;
      break;

    case M8TC_ABORT_LIFT:
      // Relative +5 mm is safe even if STOP was pressed while the test was in
      // relative XY/E mode. This move is queued by the main loop, not the LCD.
      if (m8tc_enqueue_z_relative(5.0f)) {
        m8tc_state = M8TC_ABORT_WAIT_LIFT;
        ui.set_status(F("STOP: Lifting Z 5mm"));
      }
      break;

    case M8TC_ABORT_WAIT_LIFT:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_ABORT_ABSOLUTE;
      break;

    case M8TC_ABORT_ABSOLUTE:
      if (queue.enqueue_one(F("G90"))) {
        m8tc_state = M8TC_ABORT_WAIT_ABSOLUTE;
        ui.set_status(F("STOP: Lifted / Parking"));
      }
      break;

    case M8TC_ABORT_WAIT_ABSOLUTE:
      if (!queue.has_commands_queued())
        m8tc_state = M8TC_ABORT_PARK;
      break;

    case M8TC_ABORT_PARK:
      if (m8tc_enqueue_xy(0.0f, 0.0f, 3000)) {
        m8tc_state = M8TC_ABORT_WAIT_PARK;
        ui.set_status(F("STOP: Parking X0 Y0"));
      }
      break;

    case M8TC_ABORT_WAIT_PARK:
      if (!queue.has_commands_queued()) {
        queue.inject(F("M82\\nM107"));
        m8tc_state = M8TC_IDLE;
        ui.set_status(F("Stopped / Lifted / Parked"));
        ui.completion_feedback();
        ui.refresh(LCDVIEW_CLEAR_CALL_REDRAW);
      }
      break;

'''
finish_anchor = "    case M8TC_FINISH_LIFT:\n"
if finish_anchor not in s:
    raise SystemExit("finish-state insertion point not found")
s = s.replace(finish_anchor, abort_cases + finish_anchor, 1)


# ---------------------------------------------------------------------------
# 2) LIVE NOZZLE TEMPERATURE in Setup Test Print menu.
# ---------------------------------------------------------------------------
# Refresh the running test screen about once per second so the readout changes.
replace_once(
    "void monster8_test_cube_task() {\n  if (m8tc_state == M8TC_IDLE) return;\n\n  const uint16_t print_feed",
    "void monster8_test_cube_task() {\n  if (m8tc_state == M8TC_IDLE) return;\n\n"
    "  static millis_t m8tc_next_temp_redraw = 0;\n"
    "  if (ELAPSED(millis(), m8tc_next_temp_redraw)) {\n"
    "    m8tc_next_temp_redraw = millis() + 1000UL;\n"
    "    ui.refresh();\n"
    "  }\n\n"
    "  const uint16_t print_feed",
    "live temperature redraw",
)

# Show actual nozzle temperature in both the setup and running views. The idle
# menu already has the editable target temperature; the new line is the sensor
# reading so the operator can see the hotend warming/cooling.
idle_anchor = '    EDIT_ITEM_F(int3, F("Cube Size mm"), &m8tc_size, 5, m8tc_max_size());\n'
if idle_anchor not in s:
    raise SystemExit("idle cube-size menu item not found")
s = s.replace(
    idle_anchor,
    '    STATIC_ITEM_F(F("Nozzle Now C"), SS_LEFT, i16tostr3rj(int16_t(thermalManager.degHotend(0))));\n' + idle_anchor,
    1,
)

run_anchor = '    STATIC_ITEM_F(F("Setup Test Running"));\n'
if run_anchor not in s:
    raise SystemExit("running test menu header not found")
s = s.replace(
    run_anchor,
    run_anchor + '    STATIC_ITEM_F(F("Nozzle Now C"), SS_LEFT, i16tostr3rj(int16_t(thermalManager.degHotend(0))));\n',
    1,
)


# ---------------------------------------------------------------------------
# 3) PRIME LINES: keep them outside the cube footprint.
# ---------------------------------------------------------------------------
# X0/Y0 is the cube origin. Move 8 mm in -Y before purging, then use the
# existing 2 mm spacing between lines. With 1/2/3 lines they sit at Y=-8,
# -6, and -4 mm, all outside a cube that begins at Y=0.
replace_once(
    "  M8TC_SETUP_G91,\n  M8TC_PRIME_LINE1,",
    "  M8TC_SETUP_G91,\n  M8TC_PRIME_OFFSET,\n  M8TC_PRIME_LINE1,",
    "prime offset state",
)

old_setup_g91 = '''    case M8TC_SETUP_G91:
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
'''
new_setup_g91 = '''    case M8TC_SETUP_G91:
      if (queue.enqueue_one(F("G91"))) {
        if (m8tc_prime_lines > 0) {
          m8tc_state = M8TC_PRIME_OFFSET;
          ui.set_status(F("Test: Move to prime"));
        }
        else {
          m8tc_state = M8TC_OUTER_START;
          ui.set_status(F("Printing Test Cube"));
        }
      }
      break;

    case M8TC_PRIME_OFFSET:
      if (m8tc_enqueue_xy(0.0f, -8.0f, 1800)) {
        m8tc_state = M8TC_PRIME_LINE1;
        ui.set_status(F("Test: Priming lines"));
      }
      break;
'''
replace_once(old_setup_g91, new_setup_g91, "prime offset setup")

prime_start = s.find("    case M8TC_PRIME_TO_CUBE: {")
prime_end_anchor = "\n\n    case M8TC_OUTER_START:"
prime_end = s.find(prime_end_anchor, prime_start)
if prime_start < 0 or prime_end < 0:
    raise SystemExit("mapped prime-to-cube block not found")

new_prime_return = '''    case M8TC_PRIME_TO_CUBE: {
      // Prime lines are outside the cube at negative Y. Return to X0/Y0 with
      // Z lifted first so the nozzle cannot drag across the purge material.
      const float rx = (m8tc_prime_done & 1) ? -m8tc_prime_length : 0.0f;
      const float ry = 8.0f - 2.0f * float(m8tc_prime_done > 0 ? m8tc_prime_done - 1 : 0);
      char sx[14], sy[14], cmd[120];
      dtostrf(rx, 1, 3, sx);
      dtostrf(ry, 1, 3, sy);
      snprintf_P(cmd, sizeof(cmd), PSTR("G1 Z2 F600\\nG1 X%s Y%s F3000\\nG1 Z-2 F600"), sx, sy);
      queue.inject(cmd);
      m8tc_x = m8tc_y = 0;
      m8tc_state = M8TC_OUTER_START;
      ui.set_status(F("Printing Test Cube"));
    } break;
'''
s = s[:prime_start] + new_prime_return + s[prime_end:]

p.write_text(s)
print("Fixed non-blocking STOP lift/park, live nozzle temperature, and prime lines outside cube")
