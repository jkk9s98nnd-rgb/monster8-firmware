from pathlib import Path

root = Path("MarlinSource/Marlin")
core = root / "src/MarlinCore.cpp"
ui_cpp = root / "src/lcd/marlinui.cpp"
tune = root / "src/lcd/menu/menu_tune.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
led_cpp = root / "src/feature/leds/mini12864_individual_leds.cpp"
led_menu = root / "src/lcd/menu/menu_led.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1) Automatically open Tune whenever a print starts or resumes.
# ---------------------------------------------------------------------------
replace_once(
    core,
    '#include "lcd/marlinui.h"\n',
    '#include "lcd/marlinui.h"\n\n#if HAS_MARLINUI_MENU\n  void menu_tune();\n#endif\n',
    "MarlinCore Tune menu forward declaration",
)

replace_once(
    core,
    '''void startOrResumeJob() {\n  if (!printingIsPaused()) {\n    TERN_(GCODE_REPEAT_MARKERS, repeat.reset());\n    TERN_(CANCEL_OBJECTS, cancelable.reset());\n    TERN_(LCD_SHOW_E_TOTAL, e_move_accumulator = 0);\n    TERN_(SET_REMAINING_TIME, ui.reset_remaining_time());\n  }\n  print_job_timer.start();\n}\n''',
    '''void startOrResumeJob() {\n  if (!printingIsPaused()) {\n    TERN_(GCODE_REPEAT_MARKERS, repeat.reset());\n    TERN_(CANCEL_OBJECTS, cancelable.reset());\n    TERN_(LCD_SHOW_E_TOTAL, e_move_accumulator = 0);\n    TERN_(SET_REMAINING_TIME, ui.reset_remaining_time());\n  }\n  print_job_timer.start();\n  #if HAS_MARLINUI_MENU\n    // Monster8 operator screen: when a print starts or resumes, go straight\n    // to Tune so Speed / Flow / Nozzle / Pause / Stop are immediately visible.\n    ui.goto_screen(menu_tune);\n  #endif\n}\n''',
    "auto-enter Tune on print start/resume",
)


# ---------------------------------------------------------------------------
# 2) Keep Tune on-screen while printing, but only Tune. If Mark manually backs
#    out or chooses another menu, normal Marlin timeout behavior resumes there.
# ---------------------------------------------------------------------------
replace_once(
    ui_cpp,
    'MarlinUI ui;\n',
    'MarlinUI ui;\n\n#if HAS_MARLINUI_MENU\n  void menu_tune();\n#endif\n',
    "MarlinUI Tune menu forward declaration",
)

replace_once(
    ui_cpp,
    '''        if (on_status_screen() || defer_return_to_status)\n          reset_status_timeout(ms);\n        else if (ELAPSED(ms, return_to_status_ms))\n          return_to_status();\n''',
    '''        if (on_status_screen() || defer_return_to_status\n            || (printingIsActive() && currentScreen == menu_tune))\n          reset_status_timeout(ms);\n        else if (ELAPSED(ms, return_to_status_ms))\n          return_to_status();\n''',
    "keep Tune from timing out during active print",
)


# ---------------------------------------------------------------------------
# 3) Add Pause / Resume and Stop Print controls at the top of Tune.
#    Stop keeps Marlin's existing confirmation screen and safe Monster8 abort.
# ---------------------------------------------------------------------------
replace_once(
    tune,
    '''void menu_tune() {\n  START_MENU();\n  BACK_ITEM(MSG_MAIN_MENU);\n\n  //\n  // Speed:\n''',
    '''void menu_tune() {\n  const bool m8_print_active = printingIsActive();\n  const bool m8_print_paused = printingIsPaused();\n\n  START_MENU();\n  BACK_ITEM(MSG_MAIN_MENU);\n\n  #if HAS_MEDIA\n    if (m8_print_active)\n      ACTION_ITEM(MSG_PAUSE_PRINT, ui.pause_print);\n    else if (m8_print_paused)\n      ACTION_ITEM(MSG_RESUME_PRINT, ui.resume_print);\n\n    if (m8_print_active || m8_print_paused) {\n      SUBMENU(MSG_STOP_PRINT, []{\n        MenuItem_confirm::select_screen(\n          GET_TEXT_F(MSG_BUTTON_STOP), GET_TEXT_F(MSG_BACK),\n          ui.abort_print, nullptr,\n          GET_TEXT_F(MSG_STOP_PRINT), (const char *)nullptr, F("?")\n        );\n      });\n    }\n  #endif\n\n  //\n  // Speed:\n''',
    "Pause/Resume/Stop controls in Tune",
)


# ---------------------------------------------------------------------------
# 4) After a completed LCD mesh command, save it, lift Z another 10mm, then
#    return to the user's established logical/native X0 Y0 at 40mm/s.
# ---------------------------------------------------------------------------
replace_once(
    bed,
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500")',
    'PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L%i R%i F%i B%i E V1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400")',
    "post-mesh lift and XY0 return",
)


# ---------------------------------------------------------------------------
# 5) Mini12864 V3 default LEDs: keep LED 1 (display backlight) white and turn
#    LED 2 + LED 3 (encoder/wheel LEDs) off. Bump the custom store version so
#    the first boot on this firmware intentionally adopts the new defaults.
# ---------------------------------------------------------------------------
replace_once(
    led_cpp,
    '''Mini12864LedChannel Mini12864IndividualLEDs::channel[3] = {\n  { 255, 255, 255, 255 },\n  { 255, 255, 255, 255 },\n  { 255, 255, 255, 255 }\n};\n''',
    '''Mini12864LedChannel Mini12864IndividualLEDs::channel[3] = {\n  { 255, 255, 255, 255 },\n  { 255, 255, 255,   0 },\n  { 255, 255, 255,   0 }\n};\n''',
    "Mini12864 initial wheel LEDs off",
)

replace_once(
    led_cpp,
    'constexpr uint8_t LED_STORE_VERSION = 1;\n',
    'constexpr uint8_t LED_STORE_VERSION = 2;\n',
    "LED persistent store version bump",
)

replace_once(
    led_cpp,
    '''void Mini12864IndividualLEDs::defaults() {\n  for (uint8_t i = 0; i < 3; ++i)\n    channel[i] = { 255, 255, 255, 255 };\n}\n''',
    '''void Mini12864IndividualLEDs::defaults() {\n  channel[0] = { 255, 255, 255, 255 }; // Display backlight ON\n  channel[1] = { 255, 255, 255,   0 }; // Encoder LED OFF\n  channel[2] = { 255, 255, 255,   0 }; // Encoder LED OFF\n}\n''',
    "Mini12864 default wheel LEDs off",
)

# Preserve the explicit "All White" command as truly all-white even though the
# power-on defaults are now screen-only.
replace_once(
    led_menu,
    '''static void led_all_white() {\n  mini12864IndividualLEDs.defaults();\n  mini12864IndividualLEDs.apply_all();\n}\n''',
    '''static void led_all_white() {\n  for (uint8_t i = 0; i < 3; ++i)\n    mini12864IndividualLEDs.channel[i] = { 255, 255, 255, 255 };\n  mini12864IndividualLEDs.apply_all();\n}\n''',
    "preserve All White LED command",
)


# ---------------------------------------------------------------------------
# Regression guards for the new operator UI plus previously proven safety.
# ---------------------------------------------------------------------------
core_text = core.read_text()
ui_text = ui_cpp.read_text()
tune_text = tune.read_text()
bed_text = bed.read_text()
led_text = led_cpp.read_text()
led_menu_text = led_menu.read_text()

for required in [
    'ui.goto_screen(menu_tune);',
    'do_blocking_move_to_z(m8_abort_safe_z, 10.0f);',
    'do_blocking_move_to_xy(0.0f, 0.0f, 40.0f);',
]:
    if required not in core_text:
        raise SystemExit(f"Operator UI core guard missing: {required}")

if '(printingIsActive() && currentScreen == menu_tune)' not in ui_text:
    raise SystemExit("Tune timeout guard missing")

for required in [
    'ACTION_ITEM(MSG_PAUSE_PRINT, ui.pause_print);',
    'ACTION_ITEM(MSG_RESUME_PRINT, ui.resume_print);',
    'SUBMENU(MSG_STOP_PRINT',
    'ui.abort_print',
    'EDIT_ITEM(int3, MSG_SPEED',
    'EDIT_ITEM(int3, MSG_FLOW',
]:
    if required not in tune_text:
        raise SystemExit(f"Tune menu regression guard missing: {required}")

for required in [
    'G29 P%u L%i R%i F%i B%i E V1\\nM500\\nG91\\nG1 Z10 F600\\nG90\\nG1 X0 Y0 F2400',
    'GCODES_ITEM_F(F("1 Set XY Zero"), F("G92 X0 Y0"));',
    'const int16_t map_left  = 10,',
    'map_front = 10,',
]:
    if required not in bed_text:
        raise SystemExit(f"Mesh return regression guard missing: {required}")

for required in [
    'constexpr uint8_t LED_STORE_VERSION = 2;',
    'channel[1] = { 255, 255, 255,   0 };',
    'channel[2] = { 255, 255, 255,   0 };',
]:
    if required not in led_text:
        raise SystemExit(f"LED default regression guard missing: {required}")

if 'mini12864IndividualLEDs.channel[i] = { 255, 255, 255, 255 };' not in led_menu_text:
    raise SystemExit("All White LED command regression guard missing")

print("Monster8 V8 operator UI: auto Tune, sticky Tune while printing, Pause/Stop, mesh lift+XY0, wheel LEDs off")
