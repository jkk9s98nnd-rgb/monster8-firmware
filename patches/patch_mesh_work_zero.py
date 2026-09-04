from pathlib import Path

p = Path("MarlinSource/Marlin/src/lcd/menu/menu_bed_leveling.cpp")
s = p.read_text()

# The printer now uses NO_WORKSPACE_OFFSETS, so G92 X0 Y0 sets the native
# machine position directly. Keep the bed-level motion path that was already
# proven on the machine: start probing 10mm in from the user-set origin instead
# of trying to probe exactly at X0/Y0.
start = s.find("static void m8_run_sized_mesh(const uint8_t points) {")
end = s.find("\n}\n\nstatic void m8_show_last_mesh()", start)
if start < 0 or end < 0:
    raise SystemExit("final sized mesh function not found")
end += 2

new_func = r'''static void m8_run_sized_mesh(const uint8_t points) {
  m8_probe_fail_reason = 0;
  m8_mesh_last_point = 0;

  // ONE coordinate system:
  //   user positions nozzle -> Set XY Zero -> native X0/Y0
  // The selected Map X / Map Y values are absolute limits from that zero.
  // Preserve the known-good 10mm probe inset so G29 never starts at the exact
  // corner. Example: 200x200 map probes X10..200 and Y10..200.
  const int16_t map_left  = 10,
                map_front = 10,
                map_right = m8_mesh_x_mm,
                map_back  = m8_mesh_y_mm;

  if (map_right <= map_left || map_back <= map_front) {
    ui.set_status(F("Mesh area too small"), 0);
    ui.return_to_status();
    return;
  }

  char cmd[128];
  snprintf_P(
    cmd, sizeof(cmd),
    PSTR("G28 Z\nG90\nG1 Z%i F600\nG29 P%u L%i R%i F%i B%i E V1\nM500"),
    int(m8_mesh_safe_z), points,
    int(map_left), int(map_right), int(map_front), int(map_back)
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
print("Native XY zero retained; known-good 10mm mesh inset restored")
