from pathlib import Path

root = Path('MarlinSource/Marlin')

# 1) Add BIQU MicroProbe options to Configuration.h so config.ini can enable V2.
p = root / 'Configuration.h'
s = p.read_text()
needle = "// A probe that is deployed and stowed with a solenoid pin (SOL1_PIN)\n"
insert = """/**
 * BIQU MicroProbe
 * A lightweight, solenoid-driven probe.
 * Also requires PROBE_ENABLE_DISABLE.
 */
//#define BIQU_MICROPROBE_V1  // Triggers HIGH
//#define BIQU_MICROPROBE_V2  // Triggers LOW

// A probe that is deployed and stowed with a solenoid pin (SOL1_PIN)
"""
if needle not in s:
    raise SystemExit('Configuration.h MicroProbe insertion point not found')
p.write_text(s.replace(needle, insert, 1))

# 2) Tell Marlin this is a stowable probe so M401/M402 and Z probing are compiled.
p = root / 'src/inc/Conditionals_LCD.h'
s = p.read_text()
old = "ANY(TOUCH_MI_PROBE, Z_PROBE_ALLEN_KEY, HAS_Z_SERVO_PROBE, SOLENOID_PROBE, Z_PROBE_SLED, RACK_AND_PINION_PROBE, SENSORLESS_PROBING, MAGLEV4, MAG_MOUNTED_PROBE)"
new = "ANY(TOUCH_MI_PROBE, Z_PROBE_ALLEN_KEY, HAS_Z_SERVO_PROBE, SOLENOID_PROBE, Z_PROBE_SLED, RACK_AND_PINION_PROBE, SENSORLESS_PROBING, MAGLEV4, MAG_MOUNTED_PROBE, BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)"
if old not in s:
    raise SystemExit('Conditionals_LCD.h stowable probe list not found')
p.write_text(s.replace(old, new, 1))

# IMPORTANT: Do not suppress Marlin's normal Z raise around probe deploy/stow.
# G29 uses the same deploy/stow path as M401/M402. Disabling that raise caused
# the MicroProbe pin to extend while the carriage was too close to the bed.

# 3) MicroProbe V2 needs a short wake-up period after PA8 is asserted.
p = root / 'src/module/endstops.cpp'
s = p.read_text()
old = """    #if PIN_EXISTS(PROBE_ENABLE)
      WRITE(PROBE_ENABLE_PIN, onoff);
    #endif
    resync();
"""
new = """    #if PIN_EXISTS(PROBE_ENABLE)
      WRITE(PROBE_ENABLE_PIN, onoff);
      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
        if (onoff) safe_delay(50);
      #endif
    #endif
    resync();
"""
if old not in s:
    raise SystemExit('endstops.cpp probe enable block not found')
p.write_text(s.replace(old, new, 1))

print('Applied native BIQU MicroProbe V2 support patch with normal Marlin Z clearance')
