from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_main.cpp")
s = p.read_text()

# We need to distinguish "G-code command was parsed" from "the motors have
# physically finished the move". queue.has_commands_queued() only covers the
# command queue. planner.has_blocks_queued() stays true until the planned move
# has actually run through the steppers.
if '#include "../../module/planner.h"\n' not in s:
    anchor = '#include "../../module/motion.h"\n'
    if anchor not in s:
        raise SystemExit("motion include not found")
    s = s.replace(anchor, anchor + '#include "../../module/planner.h"\n', 1)

replacements = [
    (
        '''    case M8TC_ABORT_WAIT_LIFT:\n      if (!queue.has_commands_queued())\n        m8tc_state = M8TC_ABORT_ABSOLUTE;\n      break;\n''',
        '''    case M8TC_ABORT_WAIT_LIFT:\n      // Do not allow any XY park command until the 5mm Z lift has physically\n      // completed at the steppers. The G-code queue can be empty while a\n      // planner block is still moving.\n      if (!queue.has_commands_queued() && !planner.has_blocks_queued())\n        m8tc_state = M8TC_ABORT_ABSOLUTE;\n      break;\n''',
        "stop lift physical wait",
    ),
    (
        '''    case M8TC_ABORT_WAIT_PARK:\n      if (!queue.has_commands_queued()) {\n        queue.inject(F("M82\\nM107"));\n''',
        '''    case M8TC_ABORT_WAIT_PARK:\n      if (!queue.has_commands_queued() && !planner.has_blocks_queued()) {\n        queue.inject(F("M82\\nM107"));\n''',
        "stop park physical wait",
    ),
    (
        '''    case M8TC_START_WAIT_LIFT:\n      if (!queue.has_commands_queued())\n        m8tc_state = M8TC_START_ABSOLUTE;\n      break;\n''',
        '''    case M8TC_START_WAIT_LIFT:\n      if (!queue.has_commands_queued() && !planner.has_blocks_queued())\n        m8tc_state = M8TC_START_ABSOLUTE;\n      break;\n''',
        "startup lift physical wait",
    ),
    (
        '''    case M8TC_START_WAIT_PARK:\n      if (!queue.has_commands_queued()) {\n        thermalManager.setTargetHotend(m8tc_temp, 0);\n''',
        '''    case M8TC_START_WAIT_PARK:\n      if (!queue.has_commands_queued() && !planner.has_blocks_queued()) {\n        thermalManager.setTargetHotend(m8tc_temp, 0);\n''',
        "startup park physical wait",
    ),
]

for old, new, label in replacements:
    if old not in s:
        raise SystemExit(f"{label}: expected source text not found")
    s = s.replace(old, new, 1)

p.write_text(s)
print("STOP and START now wait for physical planner completion before XY motion")
