from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")

# ---------------------------------------------------------------------------
# MicroProbe V2 reliability
# ---------------------------------------------------------------------------
# The earlier backport only waited 50ms after asserting PROBE_ENABLE. BTT
# MicroProbe V2 configurations commonly allow ~500ms for the probe electronics
# and trigger output to settle. Give deploy 500ms and stow 200ms, then resync
# the endstop state before any motion can use it.
endstops = root / "src/module/endstops.cpp"
text = endstops.read_text()
old = """      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
        if (onoff) safe_delay(50);
      #endif
"""
new = """      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
        safe_delay(onoff ? 500 : 200);
      #endif
"""
if old not in text:
    raise SystemExit("MicroProbe enable delay block not found")
endstops.write_text(text.replace(old, new, 1))

# A deliberate cold-start conditioning cycle before LCD Z homing / G29.
# M402 guarantees the control line starts LOW, then M401 drives it HIGH and
# leaves enough time for the V2 detection output to become valid before G28.
warm_home = "M402\\nG4 P250\\nM401\\nG4 P500\\nG28 Z"

# ---------------------------------------------------------------------------
# Bed leveling menu: warm the probe before Z home and before every mesh run.
# ---------------------------------------------------------------------------
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
bed_text = bed.read_text()

old_mesh = 'PSTR("G28 Z\\nG29 P%u L0 R%i F0 B%i E V1\\nM500"),'
new_mesh = 'PSTR("M402\\nG4 P250\\nM401\\nG4 P500\\nG28 Z\\nG29 P%u L0 R%i F0 B%i E V1\\nM500"),'
if old_mesh not in bed_text:
    raise SystemExit("combined mesh command not found")
bed_text = bed_text.replace(old_mesh, new_mesh, 1)

old_home = 'GCODES_ITEM_F(F("Home Z Only"), F("G28 Z"));'
if old_home not in bed_text:
    raise SystemExit("Bed Level Home Z item not found")
bed_text = bed_text.replace(old_home, f'GCODES_ITEM_F(F("Home Z Only"), F("{warm_home}"));', 1)

bed.write_text(bed_text)

# ---------------------------------------------------------------------------
# Motion menu: every LCD Home Z command gets the same cold-start conditioning.
# ---------------------------------------------------------------------------
motion = root / "src/lcd/menu/menu_motion.cpp"
motion_text = motion.read_text()
old_motion_home = 'GCODES_ITEM_F(F("Home Z Only"), F("G28 Z"));'
count = motion_text.count(old_motion_home)
if count < 1:
    raise SystemExit("No Motion Home Z items found")
motion_text = motion_text.replace(
    old_motion_home,
    f'GCODES_ITEM_F(F("Home Z Only"), F("{warm_home}"));'
)
motion.write_text(motion_text)

print(f"Applied MicroProbe V2 reliability patch: 500ms deploy settle, 200ms stow settle, warm-up before Z home and mesh ({count} Motion items)")
