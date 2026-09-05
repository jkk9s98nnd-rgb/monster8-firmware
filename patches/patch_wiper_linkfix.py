from pathlib import Path

root = Path("MarlinSource/Marlin")
g28 = root / "src/gcode/calibrate/G28.cpp"
feature_cpp = root / "src/feature/m8_wiper.cpp"
m1001 = root / "src/gcode/sd/M1001.cpp"

# The Marlin 2.1.2.8 PlatformIO source filter doesn't automatically compile a
# new arbitrary src/feature/*.cpp file. Keep the clean feature header, but fold
# the implementation into the already-compiled G28 translation unit. This is a
# link-only fix; it does not change any wiper behavior.
s = g28.read_text()
queue_inc_anchor = '#include "../gcode.h"\n'
if queue_inc_anchor not in s:
    raise SystemExit("Wiper linkfix: G28 gcode include anchor missing")
if '#include "../queue.h"' not in s:
    s = s.replace(queue_inc_anchor, queue_inc_anchor + '#include "../queue.h"\n', 1)

impl = feature_cpp.read_text()
marker = '// Physical layout agreed for the AD5X rubber wiper:'
pos = impl.find(marker)
if pos < 0:
    raise SystemExit("Wiper linkfix: implementation marker missing")
impl_body = impl[pos:]

if 'bool m8_wiper_enabled = false;' not in s:
    s += '\n\n// Monster8 wiper implementation is compiled here so it is included by the\n'
    s += '// stock Marlin 2.1.2.8 PlatformIO source filter.\n'
    s += impl_body + '\n'

g28.write_text(s)

# Guarantee a normal completion park even when Marlin's compile-time
# SD_FINISHED_RELEASECOMMAND hook is optimized away by the config parser.
# If the hot final wipe already parked X0/Y0, do not add another lift.
s = m1001.read_text()
old = '''  // Inject SD_FINISHED_RELEASECOMMAND, if any\n  #ifdef SD_FINISHED_RELEASECOMMAND\n    if (!m8_wiper_parked) process_subcommands_now(F(SD_FINISHED_RELEASECOMMAND));\n  #endif\n'''
new = '''  // Monster8 always parks safely at X0/Y0 on normal completion. If the hot\n  // final wipe already parked there, skip the duplicate G27 / extra Z lift.\n  if (!m8_wiper_parked) process_subcommands_now(F("G27"));\n'''
if old not in s:
    raise SystemExit("Wiper linkfix: expected completion block not found")
s = s.replace(old, new, 1)
m1001.write_text(s)

# Link / behavior guards.
for required in [
    'bool m8_wiper_enabled = false;',
    'void m8_wiper_before_print()',
    'bool m8_wiper_after_print()',
    'void m8_wiper_queue_test()',
    '#include "../queue.h"',
]:
    if required not in g28.read_text():
        raise SystemExit(f"Wiper linkfix guard failed: {required}")

if 'if (!m8_wiper_parked) process_subcommands_now(F("G27"));' not in m1001.read_text():
    raise SystemExit("Wiper linkfix guard failed: guaranteed completion G27 missing")

print("Wiper runtime linked into compiled G28 unit; normal SD completion now always parks exactly once")
