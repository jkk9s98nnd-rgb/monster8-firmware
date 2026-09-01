from pathlib import Path

root = Path('MarlinSource/Marlin')

# 1) Add BIQU MicroProbe options to Configuration.h so config.ini can enable V2.
p = root / 'Configuration.h'
s = p.read_text()
needle = """#if ENABLED(BD_SENSOR)\n  //#define BD_SENSOR_PROBE_NO_STOP // Probe bed without stopping at each probe point\n#endif\n\n// A probe that is deployed and stowed with a solenoid pin (SOL1_PIN)\n"""
insert = """#if ENABLED(BD_SENSOR)\n  //#define BD_SENSOR_PROBE_NO_STOP // Probe bed without stopping at each probe point\n#endif\n\n/**\n * BIQU MicroProbe\n * A lightweight, solenoid-driven probe.\n * Also requires PROBE_ENABLE_DISABLE.\n */\n//#define BIQU_MICROPROBE_V1  // Triggers HIGH\n//#define BIQU_MICROPROBE_V2  // Triggers LOW\n\n// A probe that is deployed and stowed with a solenoid pin (SOL1_PIN)\n"""
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

# 3) MicroProbe does not need the machine to move Z just to extend/retract.
#    Keep M401/M402 motionless on this machine.
p = root / 'src/module/probe.cpp'
s = p.read_text()
old = """  #if ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n    const bool z_raise_wanted = deploy;\n  #else\n    constexpr bool z_raise_wanted = true;\n  #endif\n"""
new = """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n    constexpr bool z_raise_wanted = false;\n  #elif ANY(FIX_MOUNTED_PROBE, NOZZLE_AS_PROBE) && DISABLED(PAUSE_BEFORE_DEPLOY_STOW)\n    const bool z_raise_wanted = deploy;\n  #else\n    constexpr bool z_raise_wanted = true;\n  #endif\n"""
if old not in s:
    raise SystemExit('probe.cpp deploy clearance block not found')
p.write_text(s.replace(old, new, 1))

# 4) MicroProbe V2 needs a short wake-up period after PA8 is asserted.
p = root / 'src/module/endstops.cpp'
s = p.read_text()
old = """    #if PIN_EXISTS(PROBE_ENABLE)\n      WRITE(PROBE_ENABLE_PIN, onoff);\n    #endif\n    resync();\n"""
new = """    #if PIN_EXISTS(PROBE_ENABLE)\n      WRITE(PROBE_ENABLE_PIN, onoff);\n      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)\n        if (onoff) safe_delay(50);\n      #endif\n    #endif\n    resync();\n"""
if old not in s:
    raise SystemExit('endstops.cpp probe enable block not found')
p.write_text(s.replace(old, new, 1))

print('Applied native BIQU MicroProbe V2 support patch')
