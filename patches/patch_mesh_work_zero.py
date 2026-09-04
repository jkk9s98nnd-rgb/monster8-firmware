from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_bed_leveling.cpp")
s = p.read_text()

# G29 L/R/F/B are native probe coordinates in Marlin 2.1.2.8. The LCD map,
# however, is specified in the user's logical work coordinates after G92 X0 Y0.
# Convert logical X0/Y0 to native machine coordinates, then add the selected
# map size. This makes a zero established at machine X70 Y20 with a 120x120
# map probe X70..190 and Y20..140 exactly.
if '#include "../../module/motion.h"\n' not in s:
    anchor = '#include "../../gcode/queue.h"\n'
    if anchor not in s:
        raise SystemExit("bed leveling queue include not found")
    s = s.replace(anchor, anchor + '#include "../../module/motion.h"\n', 1)

start = s.find("static void m8_run_sized_mesh(const uint8_t points) {")
end = s.find("\n}\n\nstatic void m8_show_last_mesh()", start)
if start < 0 or end < 0:
    raise SystemExit("final sized mesh function not found")
end += 2

new_func = r'''static void m8_run_sized_mesh(const uint8_t points) {
  m8_probe_fail_reason = 0;
  m8_mesh_last_point = 0;

  // The user establishes X0/Y0 with G92 at the lower-left corner of the
  // desired work area. G29's explicit bounds are native coordinates, so
  // translate logical zero back into native machine space before probing.
  const float map_left  = LOGICAL_TO_NATIVE(0.0f, X_AXIS),
              map_front = LOGICAL_TO_NATIVE(0.0f, Y_AXIS),
              map_right = map_left  + float(m8_mesh_x_mm),
              map_back  = map_front + float(m8_mesh_y_mm);

  char sl[16], sr[16], sf[16], sb[16], cmd[160];
  dtostrf(map_left,  1, 3, sl);
  dtostrf(map_right, 1, 3, sr);
  dtostrf(map_front, 1, 3, sf);
  dtostrf(map_back,  1, 3, sb);

  snprintf_P(
    cmd, sizeof(cmd),
    PSTR("G28 Z\nG90\nG1 Z%i F600\nG29 P%u L%s R%s F%s B%s E V1"),
    int(m8_mesh_safe_z), points, sl, sr, sf, sb
  );

  ui.status_printf(
    0, F("Mesh X%i-%i Y%i-%i"),
    int(map_left), int(map_right), int(map_front), int(map_back)
  );
  queue.inject(cmd);
}
'''

s = s[:start] + new_func + s[end:]
p.write_text(s)
print("Mesh bounds now follow G92 work zero and use the full selected X/Y area")
