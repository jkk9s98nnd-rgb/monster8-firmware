# Monster8 Firmware

Custom Marlin 2.1.2.8 build for MKS Monster8 V2.

Initial commissioning configuration:
- MKS Monster8 V2
- MKS Mini 12864 V3 LCD
- External TB6600 drivers for X, Y, Y2 and Z
- Creality Sprite Extruder Pro
- X/Y GT2 2 mm pitch, 20-tooth pulleys
- Z 8 mm lead screw
- Nominal 610 x 914 x 305 mm work envelope
- EEPROM enabled and steps/mm editable from the LCD
- No physical limit switches installed yet
- BIQU MicroProbe V2 reserved for a later revision
- Heated bed and spindle control reserved for later revisions

The GitHub Actions workflow compiles the official Marlin 2.1.2.8 release and publishes `mks_monster8.bin` as a build artifact.
