from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found in {path}")
    path.write_text(text.replace(old, new, 1))


g29 = Path("MarlinSource/Marlin/src/gcode/bedlevel/abl/G29.cpp")
menu = Path("MarlinSource/Marlin/src/lcd/menu/menu_probe_level.cpp")

# Make Bilinear use a runtime probe density while keeping a larger fixed
# internal mesh. The build sets GRID_MAX_POINTS_X/Y to 13 so the 3x3, 5x5,
# and 7x7 node locations all land exactly on internal mesh nodes (LCM of
# 2, 4, and 6 intervals = 12 -> 13 internal points).
replace_once(
    g29,
    """  #if ENABLED(AUTO_BED_LEVELING_LINEAR)\n    grid_count_t abl_points;\n  #elif ENABLED(AUTO_BED_LEVELING_3POINT)\n    static constexpr grid_count_t abl_points = 3;\n  #elif ABL_USES_GRID\n    static constexpr grid_count_t abl_points = GRID_MAX_POINTS;\n  #endif\n""",
    """  #if ANY(AUTO_BED_LEVELING_LINEAR, AUTO_BED_LEVELING_BILINEAR)\n    grid_count_t abl_points;\n  #elif ENABLED(AUTO_BED_LEVELING_3POINT)\n    static constexpr grid_count_t abl_points = 3;\n  #endif\n""",
    "runtime bilinear point count",
)

replace_once(
    g29,
    """    #if ENABLED(AUTO_BED_LEVELING_LINEAR)\n      bool                topography_map;\n      xy_uint8_t          grid_points;\n    #else // Bilinear\n      static constexpr xy_uint8_t grid_points = { GRID_MAX_POINTS_X, GRID_MAX_POINTS_Y };\n    #endif\n\n    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n      float Z_offset;\n      bed_mesh_t z_values;\n    #endif\n""",
    """    #if ENABLED(AUTO_BED_LEVELING_LINEAR)\n      bool                topography_map;\n      xy_uint8_t          grid_points;\n    #elif ENABLED(AUTO_BED_LEVELING_BILINEAR)\n      xy_uint8_t          grid_points;\n    #endif\n\n    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n      float Z_offset;\n      bed_mesh_t z_values, sampled_z_values;\n    #endif\n""",
    "runtime bilinear grid dimensions",
)

replace_once(
    g29,
    """#if ABL_USES_GRID && ANY(AUTO_BED_LEVELING_3POINT, AUTO_BED_LEVELING_BILINEAR)\n  constexpr xy_uint8_t G29_State::grid_points;\n  constexpr grid_count_t G29_State::abl_points;\n#endif\n""",
    """#if ENABLED(AUTO_BED_LEVELING_3POINT)\n  constexpr grid_count_t G29_State::abl_points;\n#endif\n""",
    "bilinear constexpr declarations",
)

# This CNC-style machine intentionally has no X/Y endstops. X/Y are manually
# referenced before mesh probing, so G29 must only require Z to have been homed.
replace_once(
    g29,
    "if (motion.homing_needed_error()) G29_RETURN(false, false);",
    "if (motion.homing_needed_error(_BV(Z_AXIS))) G29_RETURN(false, false);",
    "Z-only G29 homing requirement",
)

replace_once(
    g29,
    """    #elif ENABLED(AUTO_BED_LEVELING_BILINEAR)\n\n      abl.Z_offset = parser.linearval('Z');\n\n    #endif\n""",
    """    #elif ENABLED(AUTO_BED_LEVELING_BILINEAR)\n\n      abl.Z_offset = parser.linearval('Z');\n\n      // Monster8 selectable Bilinear probe density. The internal correction\n      // mesh stays fixed-size; the sampled surface is interpolated into it.\n      const uint8_t requested_points = parser.byteval('P', 7);\n      if (NONE(requested_points == 3, requested_points == 5, requested_points == 7)) {\n        SERIAL_ECHOLNPGM(GCODE_ERR_MSG(\"Bilinear P must be 3, 5, or 7.\"));\n        G29_RETURN(false, false);\n      }\n      if (requested_points > GRID_MAX_POINTS_X || requested_points > GRID_MAX_POINTS_Y) {\n        SERIAL_ECHOLNPGM(GCODE_ERR_MSG(\"Selected Bilinear grid exceeds internal mesh size.\"));\n        G29_RETURN(false, false);\n      }\n      abl.grid_points.set(requested_points, requested_points);\n      abl.abl_points = grid_count_t(requested_points) * requested_points;\n\n    #endif\n""",
    "parse selectable bilinear density",
)

replace_once(
    g29,
    """    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n      if (!abl.dryrun && (abl.gridSpacing != bedlevel.grid_spacing || abl.probe_position_lf != bedlevel.grid_start)) {\n        reset_bed_level();      // Reset grid to 0.0 or \"not probed\". (Also disables ABL)\n        abl.reenable = false;   // Can't re-enable (on error) until the new grid is written\n      }\n      // Pre-populate local Z values from the stored mesh\n      TERN_(IS_KINEMATIC, COPY(abl.z_values, bedlevel.z_values));\n    #endif\n""",
    """    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n      if (!abl.dryrun) {\n        reset_bed_level();      // Start every selected mesh with fresh data.\n        abl.reenable = false;\n      }\n    #endif\n""",
    "fresh bilinear mesh start",
)

# Store raw sampled points separately. They are expanded into the fixed internal
# mesh only after probing completes.
text = g29.read_text()
needle = "abl.z_values[abl.meshCount.x][abl.meshCount.y] = newz;"
if needle not in text:
    raise SystemExit("manual bilinear sample store: expected source text not found")
text = text.replace(needle, "abl.sampled_z_values[abl.meshCount.x][abl.meshCount.y] = newz;", 1)
needle = "abl.z_values[abl.meshCount.x][abl.meshCount.y] = z;"
if needle not in text:
    raise SystemExit("automatic bilinear sample store: expected source text not found")
text = text.replace(needle, "abl.sampled_z_values[abl.meshCount.x][abl.meshCount.y] = z;", 1)
g29.write_text(text)

replace_once(
    g29,
    """    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n\n      if (abl.dryrun)\n        bedlevel.print_leveling_grid(&abl.z_values);\n      else {\n        bedlevel.set_grid(abl.gridSpacing, abl.probe_position_lf);\n        COPY(bedlevel.z_values, abl.z_values);\n        TERN_(IS_KINEMATIC, bedlevel.extrapolate_unprobed_bed_level());\n        bedlevel.refresh_bed_level();\n\n        bedlevel.print_leveling_grid();\n      }\n\n    #elif ENABLED(AUTO_BED_LEVELING_LINEAR)\n""",
    """    #if ENABLED(AUTO_BED_LEVELING_BILINEAR)\n\n      // Expand the selected 3x3 / 5x5 / 7x7 sampled Bilinear surface into\n      // the fixed 13x13 internal mesh. Because 12 is divisible by 2, 4, and\n      // 6, every selected sample node is represented exactly. The values\n      // between sample nodes are ordinary bilinear interpolation.\n      for (uint8_t ix = 0; ix < GRID_MAX_POINTS_X; ++ix) {\n        const float sx = float(ix) * float(abl.grid_points.x - 1) / float(GRID_MAX_POINTS_X - 1);\n        const uint8_t x0 = uint8_t(sx), x1 = _MIN(uint8_t(x0 + 1), uint8_t(abl.grid_points.x - 1));\n        const float fx = sx - x0;\n        for (uint8_t iy = 0; iy < GRID_MAX_POINTS_Y; ++iy) {\n          const float sy = float(iy) * float(abl.grid_points.y - 1) / float(GRID_MAX_POINTS_Y - 1);\n          const uint8_t y0 = uint8_t(sy), y1 = _MIN(uint8_t(y0 + 1), uint8_t(abl.grid_points.y - 1));\n          const float fy = sy - y0;\n\n          const float z00 = abl.sampled_z_values[x0][y0],\n                      z10 = abl.sampled_z_values[x1][y0],\n                      z01 = abl.sampled_z_values[x0][y1],\n                      z11 = abl.sampled_z_values[x1][y1],\n                      za  = z00 + (z10 - z00) * fx,\n                      zb  = z01 + (z11 - z01) * fx;\n          abl.z_values[ix][iy] = za + (zb - za) * fy;\n        }\n      }\n\n      xy_float_t full_grid_spacing;\n      full_grid_spacing.set(\n        (abl.probe_position_rb.x - abl.probe_position_lf.x) / (GRID_MAX_POINTS_X - 1),\n        (abl.probe_position_rb.y - abl.probe_position_lf.y) / (GRID_MAX_POINTS_Y - 1)\n      );\n\n      if (abl.dryrun)\n        bedlevel.print_leveling_grid(&abl.z_values);\n      else {\n        bedlevel.set_grid(full_grid_spacing, abl.probe_position_lf);\n        COPY(bedlevel.z_values, abl.z_values);\n        TERN_(IS_KINEMATIC, bedlevel.extrapolate_unprobed_bed_level());\n        bedlevel.refresh_bed_level();\n\n        bedlevel.print_leveling_grid();\n      }\n\n    #elif ENABLED(AUTO_BED_LEVELING_LINEAR)\n""",
    "interpolate selected bilinear grid",
)

# Document P for Bilinear as well as Linear.
replace_once(
    g29,
    """ *   With AUTO_BED_LEVELING_LINEAR:\n *     P<int>  Set the size of the grid that will be probed (P x P points)\n *             Example: G29 P4\n""",
    """ *   With AUTO_BED_LEVELING_LINEAR:\n *     P<int>  Set the size of the grid that will be probed (P x P points)\n *             Example: G29 P4\n""",
    "G29 documentation anchor",
)

# LCD: never offer plain G28 on this machine. Add Z-only homing and three
# explicit Bilinear mesh choices. Each run saves the resulting mesh to EEPROM.
replace_once(
    menu,
    """    #if NONE(PROBE_MANUALLY, MESH_BED_LEVELING)\n      if (!is_trusted) GCODES_ITEM(MSG_AUTO_HOME, FPSTR(G28_STR));\n    #endif\n""",
    """    #if NONE(PROBE_MANUALLY, MESH_BED_LEVELING)\n      GCODES_ITEM_F(F(\"Home Z Only\"), F(\"G28 Z\"));\n    #endif\n""",
    "LCD Z-only home item",
)

replace_once(
    menu,
    """      #else\n        // Automatic leveling can just run the G-code\n        GCODES_ITEM(MSG_LEVEL_BED, is_homed ? F(\"G29\") : F(\"G29N\"));\n      #endif\n""",
    """      #else\n        // Monster8 selectable Bilinear mesh density. X/Y are manually\n        // referenced; each sequence homes only Z, probes, then saves EEPROM.\n        GCODES_ITEM_F(F(\"Run 3x3 Mesh\"), F(\"G28 Z\\nG29 P3\\nM500\"));\n        GCODES_ITEM_F(F(\"Run 5x5 Mesh\"), F(\"G28 Z\\nG29 P5\\nM500\"));\n        GCODES_ITEM_F(F(\"Run 7x7 Mesh\"), F(\"G28 Z\\nG29 P7\\nM500\"));\n        GCODES_ITEM_F(F(\"Leveling ON\"),  F(\"M420 S1\"));\n        GCODES_ITEM_F(F(\"Leveling OFF\"), F(\"M420 S0\"));\n        #if ENABLED(BABYSTEP_ZPROBE_OFFSET)\n          GCODES_ITEM_F(F(\"Z Offset +0.10\"), F(\"M290 Z0.10\"));\n          GCODES_ITEM_F(F(\"Z Offset -0.10\"), F(\"M290 Z-0.10\"));\n        #endif\n      #endif\n""",
    "LCD selectable mesh items",
)

print("Selectable Bilinear mesh patch applied: 3x3 / 5x5 / 7x7")
