from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Internal test-print extrusion pressure management.
#
# Symptoms this addresses:
# - first prime line can travel a long distance before plastic starts
# - first few mm of each new layer can be dry after a non-extruding move
#
# Keep the user's calibrated E-steps and Flow untouched. Instead:
# 1) preload a user-selectable amount before the first prime line,
# 2) retract before every layer change to stop the nozzle draining,
# 3) restore that retract plus a small user-selectable extra restart before the
#    next perimeter begins.
# ---------------------------------------------------------------------------

replace_once(
    'static bool m8tc_top_fill = false;    // solid top skin; OFF = open top\n',
    'static bool m8tc_top_fill = false;    // solid top skin; OFF = open top\n'
    'static int16_t m8tc_start_preload = 8;          // mm filament before first prime line\n'
    'static int16_t m8tc_travel_retract_tenths = 8; // 0.1mm units; 8 = 0.8mm retract\n'
    'static int16_t m8tc_layer_restart_tenths = 5;  // extra 0.1mm units after unretract\n',
    'pressure variables',
)

# Add state for initial preload and controlled layer retract/restart.
replace_once(
    '  M8TC_SETUP_G91,\n  M8TC_PRIME_OFFSET,\n  M8TC_PRIME_LINE1,',
    '  M8TC_SETUP_G91,\n  M8TC_PRIME_OFFSET,\n  M8TC_PRIME_PRELOAD,\n  M8TC_PRIME_LINE1,',
    'prime preload enum',
)

replace_once(
    '  M8TC_INFILL_RETURN,\n  M8TC_NEXT_LAYER,\n  M8TC_LAYER_Z,\n',
    '  M8TC_INFILL_RETURN,\n  M8TC_LAYER_RETRACT,\n  M8TC_NEXT_LAYER,\n  M8TC_LAYER_Z,\n  M8TC_LAYER_RESTART,\n',
    'layer pressure enum',
)

# Initial preload happens at the start of the waste prime strip, not on the
# actual part. This turns the beginning of the prime line into useful purge
# instead of spending the first 50-100mm rebuilding pressure.
old_prime_offset = '''    case M8TC_PRIME_OFFSET:
      if (m8tc_enqueue_xy(0.0f, -8.0f, 1800)) {
        m8tc_state = M8TC_PRIME_LINE1;
        ui.set_status(F("Test: Priming lines"));
      }
      break;
'''
new_prime_offset = '''    case M8TC_PRIME_OFFSET:
      if (m8tc_enqueue_xy(0.0f, -8.0f, 1800)) {
        m8tc_state = M8TC_PRIME_PRELOAD;
        ui.set_status(F("Test: Preloading nozzle"));
      }
      break;

    case M8TC_PRIME_PRELOAD:
      if (m8tc_start_preload <= 0 || m8tc_enqueue_e(float(m8tc_start_preload), 180)) {
        m8tc_state = M8TC_PRIME_LINE1;
        ui.set_status(F("Test: Priming lines"));
      }
      break;
'''
replace_once(old_prime_offset, new_prime_offset, 'initial pressure preload')

# When sparse infill is disabled, still go through the controlled layer-change
# retract. That keeps behavior consistent for hollow/open tests too.
replace_once(
    '        m8tc_infill_count = 0;\n        m8tc_state = M8TC_NEXT_LAYER;\n        break;\n',
    '        m8tc_infill_count = 0;\n        m8tc_state = M8TC_LAYER_RETRACT;\n        break;\n',
    'no-infill layer retract transition',
)

# After an infill return, use the same controlled pressure cycle.
replace_once(
    '''    case M8TC_INFILL_RETURN:
      if (m8tc_enqueue_xy(-m8tc_x, -m8tc_y, 3000)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_NEXT_LAYER;
      }
      break;

    case M8TC_NEXT_LAYER:
''',
    '''    case M8TC_INFILL_RETURN:
      if (m8tc_enqueue_xy(-m8tc_x, -m8tc_y, 3000)) {
        m8tc_x = m8tc_y = 0;
        m8tc_state = M8TC_LAYER_RETRACT;
      }
      break;

    case M8TC_LAYER_RETRACT: {
      const float r = 0.1f * float(m8tc_travel_retract_tenths);
      if (r <= 0.0f || m8tc_enqueue_e(-r, 1800))
        m8tc_state = M8TC_NEXT_LAYER;
    } break;

    case M8TC_NEXT_LAYER:
''',
    'layer retract state',
)

# Restore the travel retract only after Z has moved to the new layer, then add
# a small extra restart amount. This means the very first perimeter segment is
# already pressurized instead of rebuilding pressure while moving.
replace_once(
    '''    case M8TC_LAYER_Z:
      if (m8tc_enqueue_z_relative(m8tc_layer_h))
        m8tc_state = M8TC_OUTER_START;
      break;

    case M8TC_FINISH_LIFT:
''',
    '''    case M8TC_LAYER_Z:
      if (m8tc_enqueue_z_relative(m8tc_layer_h))
        m8tc_state = M8TC_LAYER_RESTART;
      break;

    case M8TC_LAYER_RESTART: {
      const float restore = 0.1f * float(m8tc_travel_retract_tenths + m8tc_layer_restart_tenths);
      if (restore <= 0.0f || m8tc_enqueue_e(restore, 1200))
        m8tc_state = M8TC_OUTER_START;
    } break;

    case M8TC_FINISH_LIFT:
''',
    'layer pressure restart state',
)

# LCD tuning controls so pressure can be dialed in without another firmware
# rebuild. Start Preload is whole mm of filament; the two layer values are
# tenths of a millimeter to allow fine direct-drive tuning.
replace_once(
    '    EDIT_ITEM_F(bool, F("Top Fill"), &m8tc_top_fill);\n',
    '    EDIT_ITEM_F(bool, F("Top Fill"), &m8tc_top_fill);\n'
    '    EDIT_ITEM_F(int3, F("Start Preload mm"), &m8tc_start_preload, 0, 20);\n'
    '    EDIT_ITEM_F(int3, F("Travel Retr x0.1"), &m8tc_travel_retract_tenths, 0, 20);\n'
    '    EDIT_ITEM_F(int3, F("Layer Restart x0.1"), &m8tc_layer_restart_tenths, 0, 20);\n',
    'pressure tuning LCD items',
)

p.write_text(s)
print("Added adjustable start preload and layer retract/restart pressure management")
