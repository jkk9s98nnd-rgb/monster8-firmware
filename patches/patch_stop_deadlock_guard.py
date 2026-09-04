from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)

# Add a dedicated hard-stop state. The LCD callback should only request STOP;
# the regular firmware task performs quickstop_stepper() after the callback
# has returned, avoiding a planner synchronize while the LCD owns the menu.
replace_once(
    "  M8TC_ABORT_RELATIVE,\n",
    "  M8TC_ABORT_HARDSTOP,\n  M8TC_ABORT_RELATIVE,\n",
    "abort hardstop state",
)

old_stop = '''static void m8tc_stop() {
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

new_stop = '''static void m8tc_stop() {
  if (m8tc_state == M8TC_IDLE) return;

  // Cancel every source of queued test G-code immediately. queue.clear() only
  // clears the normal ring buffer; the test cube also uses the SRAM injected
  // command buffer, so explicitly clear both injection buffers too.
  queue.inject_P(nullptr);
  queue.inject("");
  queue.clear();
  thermalManager.disable_all_heaters();

  // Never call quickstop_stepper() from the LCD callback. Marlin's quick stop
  // synchronizes the planner, which can block the menu callback at an unlucky
  // point in motion processing. Request the hard stop and let the normal
  // firmware task execute it on the next loop pass.
  m8tc_state = M8TC_ABORT_HARDSTOP;
  ui.set_status(F("STOP: Cancelling"));
  ui.refresh(LCDVIEW_CLEAR_CALL_REDRAW);
}
'''
replace_once(old_stop, new_stop, "nonblocking LCD stop callback")

anchor = '''    case M8TC_ABORT_RELATIVE:
'''
if anchor not in s:
    raise SystemExit("abort relative case not found")

hardstop_case = '''    case M8TC_ABORT_HARDSTOP:
      // Main-loop context is safe for Marlin's planner synchronization.
      quickstop_stepper();

      // Clear again after the hard stop so no command that slipped in during
      // the button callback can survive and restart test motion.
      queue.inject_P(nullptr);
      queue.inject("");
      queue.clear();

      m8tc_state = M8TC_ABORT_RELATIVE;
      ui.set_status(F("STOP: Lifting clear"));
      break;

'''
s = s.replace(anchor, hardstop_case + anchor, 1)

p.write_text(s)
print("STOP now clears all command sources and defers quickstop out of LCD callback")
