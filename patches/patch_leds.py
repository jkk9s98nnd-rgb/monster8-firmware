from pathlib import Path

p = Path('MarlinSource/Marlin/src/feature/leds/leds.cpp')
s = p.read_text()

anchor = '#include "leds.h"\n'
include_block = (
    '#include "leds.h"\n'
    '#include "mini12864_individual_leds.h"\n'
    '#include "mini12864_individual_leds.cpp"\n'
)
if 'mini12864_individual_leds.cpp' not in s:
    if anchor not in s:
        raise SystemExit('LED include patch anchor not found')
    # Remove an earlier header-only insertion if present, then install one deterministic block.
    s = s.replace(anchor + '#include "mini12864_individual_leds.h"\n', anchor, 1)
    s = s.replace(anchor, include_block, 1)

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
