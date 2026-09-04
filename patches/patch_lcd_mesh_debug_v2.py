from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


root = Path("MarlinSource/Marlin")
probe = root / "src/module/probe.cpp"
bed = root / "src/lcd/menu/menu_bed_leveling.cpp"
g29 = root / "src/gcode/bedlevel/abl/G29.cpp"

# Shared state. These values only live for the current power-on session.
replace_once(
    probe,
    "Probe probe;\n\nxyz_pos_t Probe::offset; // Initialized by settings.load\n",
    """Probe probe;

#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
  int16_t m8_mesh_safe_z = 10;      // LCD adjustable 6..20 mm
  uint8_t m8_probe_fail_reason = 0; // 1 pretrigger, 2 no trigger, 3 early trigger
  uint8_t m8_mesh_last_point = 0;
  int16_t m8_mesh_last_x = 0, m8_mesh_last_y = 0;
#endif

xyz_pos_t Probe::offset; // Initialized by settings.load
""",
    "mesh diagnostic globals",
)

# Marlin's normal deploy/stow path already raises Z. Use the LCD-selected
# height for this MicroProbe instead of the compile-time constant.
replace_once(
    probe,
    """  if (z_raise_wanted)
    do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));
""",
    """  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
    if (z_raise_wanted) do_z_raise(float(m8_mesh_safe_z));
  #else
    if (z_raise_wanted)
      do_z_raise(_MAX(Z_CLEARANCE_BETWEEN_PROBES, Z_CLEARANCE_DEPLOY_PROBE));
  #endif
""",
    "runtime deploy/stow clearance",
)

# Also use the same height if a probe operation requests a raise rather than
# a full stow between points.
replace_once(
    probe,
    """    if (raise_after == PROBE_PT_RAISE)
      do_blocking_move_to_z(current_position.z + Z_CLEARANCE_BETWEEN_PROBES, z_probe_fast_mm_s);
""",
    """    if (raise_after == PROBE_PT_RAISE) {
      #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
        do_blocking_move_to_z(current_position.z + float(m8_mesh_safe_z), z_probe_fast_mm_s);
      #else
        do_blocking_move_to_z(current_position.z + Z_CLEARANCE_BETWEEN_PROBES, z_probe_fast_mm_s);
      #endif
    }
""",
    "runtime between-point clearance",
)

# Record a fresh reason for every physical probe cycle.
replace_once(
    probe,
    """float Probe::run_z_probe(const bool sanity_check/*=true*/) {
  DEBUG_SECTION(log_probe, "Probe::run_z_probe", DEBUGGING(LEVELING));
""",
    """float Probe::run_z_probe(const bool sanity_check/*=true*/) {
  DEBUG_SECTION(log_probe, "Probe::run_z_probe", DEBUGGING(LEVELING));
  #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
    m8_probe_fail_reason = 0;
  #endif
""",
    "reset probe failure reason",
)

# patch_probe_mesh_reliability.py installs this pre-descent safety check.
replace_once(
    probe,
    """    if (PROBE_TRIGGERED()) {
      SERIAL_ERROR_MSG("MicroProbe triggered before Z move");
      LCD_ALERTMESSAGE_F("Probe state error");
      return true;
    }
""",
    """    if (PROBE_TRIGGERED()) {
      m8_probe_fail_reason = 1;
      SERIAL_ERROR_MSG("MicroProbe triggered before Z move");
      return true;
    }
""",
    "record pretrigger",
)

replace_once(
    probe,
    """    return probe_fail || early_fail;
  };
""",
    """    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
      if (!m8_probe_fail_reason) {
        if (probe_fail) m8_probe_fail_reason = 2;
        else if (early_fail) m8_probe_fail_reason = 3;
      }
    #endif
    return probe_fail || early_fail;
  };
""",
    "record no-trigger or early-trigger",
)

# G29 sees the shared state.
replace_once(
    g29,
    "#include \"../../../core/debug_out.h\"\n\n#if ABL_USES_GRID\n",
    """#include "../../../core/debug_out.h"

#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
  extern int16_t m8_mesh_safe_z;
  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;
  extern int16_t m8_mesh_last_x, m8_mesh_last_y;
#endif

#if ABL_USES_GRID
""",
    "G29 diagnostic externs",
)

# Show point number and target coordinates continuously. If probing fails,
# replace it with a human-readable reason that remains visible on the LCD.
replace_once(
    g29,
    """          if (abl.verbose_level) SERIAL_ECHOLNPGM("Probing mesh point ", pt_index, "/", abl.abl_points, ".");
          TERN_(HAS_STATUS_MESSAGE, ui.status_printf(0, F(S_FMT " %i/%i"), GET_TEXT(MSG_PROBING_POINT), int(pt_index), int(abl.abl_points)));

          abl.measured_z = faux ? 0.001f * random(-100, 101) : probe.probe_at_point(abl.probePos, raise_after, abl.verbose_level);

          if (isnan(abl.measured_z)) {
            set_bed_leveling_enabled(abl.reenable);
            break; // Breaks out of both loops
          }
""",
    """          if (abl.verbose_level) SERIAL_ECHOLNPGM("Probing mesh point ", pt_index, "/", abl.abl_points, ".");
          #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
            m8_mesh_last_point = pt_index;
            m8_mesh_last_x = int16_t(abl.probePos.x);
            m8_mesh_last_y = int16_t(abl.probePos.y);
            ui.status_printf(0, F("P%i/%i X%i Y%i"), int(pt_index), int(abl.abl_points), int(m8_mesh_last_x), int(m8_mesh_last_y));
          #else
            TERN_(HAS_STATUS_MESSAGE, ui.status_printf(0, F(S_FMT " %i/%i"), GET_TEXT(MSG_PROBING_POINT), int(pt_index), int(abl.abl_points)));
          #endif

          abl.measured_z = faux ? 0.001f * random(-100, 101) : probe.probe_at_point(abl.probePos, raise_after, abl.verbose_level);

          if (isnan(abl.measured_z)) {
            set_bed_leveling_enabled(abl.reenable);
            #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
              if (m8_probe_fail_reason == 1) ui.set_status(F("MESH FAIL PRETRIGGER"), 0);
              else if (m8_probe_fail_reason == 2) ui.set_status(F("MESH FAIL NO TRIGGER"), 0);
              else if (m8_probe_fail_reason == 3) ui.set_status(F("MESH FAIL EARLY TRIG"), 0);
              else ui.set_status(F("MESH FAIL PROBE"), 0);
            #endif
            break; // Breaks out of both loops
          }
""",
    "live mesh point and failure reason",
)

# Don't immediately wipe our result message at the end of automatic probing.
replace_once(
    g29,
    """    TERN_(HAS_STATUS_MESSAGE, ui.reset_status());

    // Stow the probe. No raise for FIX_MOUNTED_PROBE.
""",
    """    #if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
      if (!isnan(abl.measured_z))
        ui.status_printf(0, F("MESH OK %i/%i"), int(abl.abl_points), int(abl.abl_points));
    #else
      TERN_(HAS_STATUS_MESSAGE, ui.reset_status());
    #endif

    // Stow the probe. No raise for FIX_MOUNTED_PROBE.
""",
    "preserve final mesh result",
)

# Bed Level Setup gets the adjustable height and a recall button.
replace_once(
    bed,
    "#include \"../../gcode/queue.h\"\n",
    """#include "../../gcode/queue.h"

#if ANY(BIQU_MICROPROBE_V1, BIQU_MICROPROBE_V2)
  extern int16_t m8_mesh_safe_z;
  extern uint8_t m8_probe_fail_reason, m8_mesh_last_point;
  extern int16_t m8_mesh_last_x, m8_mesh_last_y;
#endif
""",
    "Bed Level Setup diagnostic externs",
)

replace_once(
    bed,
    """    PSTR("G28 Z\\nG90\\nG1 Z15 F600\\nG29 P%u L10 R%i F10 B%i E V1"),
    points, int(map_right), int(map_back)
""",
    """    PSTR("G28 Z\\nG90\\nG1 Z%i F600\\nG29 P%u L10 R%i F10 B%i E V1"),
    int(m8_mesh_safe_z), points, int(map_right), int(map_back)
""",
    "LCD-selected initial safe Z",
)

replace_once(
    bed,
    "  ui.set_status(F(\"Mesh: Z15 safe travel\"));\n",
    "  ui.status_printf(0, F(\"Mesh Safe Z %imm\"), int(m8_mesh_safe_z));\n",
    "safe Z start status",
)

replace_once(
    bed,
    "static void m8_run_mesh_3() { m8_run_sized_mesh(3); }\n",
    """static void m8_show_last_mesh() {
  if (!m8_mesh_last_point) ui.set_status(F("No mesh run yet"), 0);
  else if (m8_probe_fail_reason == 1) ui.status_printf(0, F("P%i X%i Y%i PRETRIG"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));
  else if (m8_probe_fail_reason == 2) ui.status_printf(0, F("P%i X%i Y%i NO TRIG"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));
  else if (m8_probe_fail_reason == 3) ui.status_printf(0, F("P%i X%i Y%i EARLY"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));
  else ui.status_printf(0, F("Last P%i X%i Y%i OK"), int(m8_mesh_last_point), int(m8_mesh_last_x), int(m8_mesh_last_y));
  ui.return_to_status();
}

static void m8_run_mesh_3() { m8_run_sized_mesh(3); }
""",
    "Show Last Mesh helper",
)

replace_once(
    bed,
    """    EDIT_ITEM_F(int3, F("Map X mm"), &m8_mesh_x_mm, 40, 610);
    EDIT_ITEM_F(int3, F("Map Y mm"), &m8_mesh_y_mm, 40, 914);
    ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);
""",
    """    EDIT_ITEM_F(int3, F("Map X mm"), &m8_mesh_x_mm, 40, 610);
    EDIT_ITEM_F(int3, F("Map Y mm"), &m8_mesh_y_mm, 40, 914);
    EDIT_ITEM_F(int3, F("Mesh Safe Z mm"), &m8_mesh_safe_z, 6, 20);
    ACTION_ITEM_F(F("Show Last Mesh"), m8_show_last_mesh);
    ACTION_ITEM_F(F("Run 3x3 Mesh"), m8_run_mesh_3);
""",
    "LCD safe Z and recall controls",
)

# Start every run with a clean result state. Hook only the stable function
# signature so comments added by earlier patches don't matter.
replace_once(
    bed,
    "static void m8_run_sized_mesh(const uint8_t points) {\n",
    """static void m8_run_sized_mesh(const uint8_t points) {
  m8_probe_fail_reason = 0;
  m8_mesh_last_point = 0;
""",
    "reset last mesh result",
)

print("Added adjustable Mesh Safe Z and LCD-only mesh point/failure diagnostics")
