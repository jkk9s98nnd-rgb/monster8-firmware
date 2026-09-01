from pathlib import Path

p = Path('MarlinSource/Marlin/src/feature/leds/leds.cpp')
s = p.read_text()

anchor = '#include "leds.h"\n'
if 'mini12864_individual_leds.h' not in s:
    if anchor not in s:
        raise SystemExit('LED include patch anchor not found')
    s = s.replace(anchor, anchor + '#include "mini12864_individual_leds.h"\n', 1)

anchor2 = '  TERN_(LED_USER_PRESET_STARTUP, set_default());\n'
insert = (
    '  TERN_(LED_USER_PRESET_STARTUP, set_default());\n'
    '  #if ENABLED(MKS_MINI_12864_V3) && ENABLED(NEOPIXEL_LED)\n'
    '    mini12864IndividualLEDs.load();\n'
    '  #endif\n'
)
if 'mini12864IndividualLEDs.load();' not in s:
    if anchor2 not in s:
        raise SystemExit('LED setup patch anchor not found')
    s = s.replace(anchor2, insert, 1)

p.write_text(s)
