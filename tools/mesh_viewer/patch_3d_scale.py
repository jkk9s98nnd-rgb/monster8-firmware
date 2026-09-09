from pathlib import Path


viewer = Path("tools/mesh_viewer/monster8_mesh_viewer.py")


def replace_once(old: str, new: str, label: str) -> None:
    text = viewer.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"{label}: expected source text not found")
    viewer.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    '''        self.file_var = tk.StringVar(value="No mesh loaded")
        self.status_var = tk.StringVar(value="Open a MESH####.CSV file from the Monster8 SD card.")
''',
    '''        self.file_var = tk.StringVar(value="No mesh loaded")
        self.status_var = tk.StringVar(value="Open a MESH####.CSV file from the Monster8 SD card.")

        # Visual-only 3D scaling. This never changes mesh measurements or analysis.
        self.z_scale_var = tk.DoubleVar(value=1.0)
        self.z_scale_label_var = tk.StringVar(value="1.0x")
''',
    "3D scale variables",
)

replace_once(
    '''    def _build_3d_tab(self):
        self.fig3d = Figure(figsize=(8, 6), dpi=100)
        self.ax3d = self.fig3d.add_subplot(111, projection="3d")
        self.canvas3d = FigureCanvasTkAgg(self.fig3d, master=self.tab_3d)
        self.canvas3d.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas3d, self.tab_3d, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)
''',
    '''    def _build_3d_tab(self):
        controls = ttk.Frame(self.tab_3d, padding=(10, 8))
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="3D Z scale:").pack(side=tk.LEFT)
        scale = ttk.Scale(
            controls,
            from_=0.25,
            to=10.0,
            variable=self.z_scale_var,
            command=self._on_z_scale_changed,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))

        self.z_scale_spin = ttk.Spinbox(
            controls,
            from_=0.10,
            to=50.0,
            increment=0.10,
            width=7,
            textvariable=self.z_scale_var,
            command=self._apply_z_scale_entry,
        )
        self.z_scale_spin.pack(side=tk.LEFT)
        self.z_scale_spin.bind("<Return>", self._apply_z_scale_entry)
        self.z_scale_spin.bind("<FocusOut>", self._apply_z_scale_entry)

        ttk.Label(controls, textvariable=self.z_scale_label_var, width=7, anchor=tk.CENTER).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(controls, text="0.5x", width=5, command=lambda: self._set_z_scale(0.5)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="1x", width=4, command=lambda: self._set_z_scale(1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="2x", width=4, command=lambda: self._set_z_scale(2.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="5x", width=4, command=lambda: self._set_z_scale(5.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="10x", width=5, command=lambda: self._set_z_scale(10.0)).pack(side=tk.LEFT, padx=2)

        ttk.Label(
            self.tab_3d,
            text="Z scale changes only the 3D appearance. All displayed measurements and calculations remain the true measured millimeters.",
            padding=(10, 0, 10, 4),
        ).pack(fill=tk.X)

        self.fig3d = Figure(figsize=(8, 6), dpi=100)
        self.ax3d = self.fig3d.add_subplot(111, projection="3d")
        self.canvas3d = FigureCanvasTkAgg(self.fig3d, master=self.tab_3d)
        self.canvas3d.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas3d, self.tab_3d, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)
''',
    "3D scale controls",
)

replace_once(
    '''    def refresh_3d(self):
        self.ax3d.clear()
        if self.points is None:
            self.canvas3d.draw_idle()
            return
        xs, ys, zg = grid_from_points(self.points)
        xx, yy = np.meshgrid(xs, ys)
        self.ax3d.plot_surface(xx, yy, zg, alpha=0.78, linewidth=0.4, edgecolor="k")
        self.ax3d.scatter(self.points[:, 0], self.points[:, 1], self.points[:, 2], s=25)
        self.ax3d.set_title("Measured bed surface")
        self.ax3d.set_xlabel("X (mm)")
        self.ax3d.set_ylabel("Y (mm)")
        self.ax3d.set_zlabel("Measured Z (mm)")
        self.canvas3d.draw_idle()
''',
    '''    def _validated_z_scale(self):
        try:
            value = float(self.z_scale_var.get())
        except (ValueError, tk.TclError):
            value = 1.0
        return max(0.10, min(50.0, value))

    def _set_z_scale(self, value):
        value = max(0.10, min(50.0, float(value)))
        self.z_scale_var.set(value)
        self.z_scale_label_var.set(f"{value:.1f}x")
        self.refresh_3d()

    def _on_z_scale_changed(self, value):
        try:
            value = float(value)
        except ValueError:
            return
        self.z_scale_label_var.set(f"{value:.1f}x")
        self.refresh_3d()

    def _apply_z_scale_entry(self, _event=None):
        self._set_z_scale(self._validated_z_scale())

    def refresh_3d(self):
        # Preserve the camera angle while changing the visual scale.
        elev = getattr(self.ax3d, "elev", 30)
        azim = getattr(self.ax3d, "azim", -60)

        self.ax3d.clear()
        if self.points is None:
            self.canvas3d.draw_idle()
            return

        xs, ys, zg = grid_from_points(self.points)
        xx, yy = np.meshgrid(xs, ys)
        self.ax3d.plot_surface(xx, yy, zg, alpha=0.78, linewidth=0.4, edgecolor="k")
        self.ax3d.scatter(self.points[:, 0], self.points[:, 1], self.points[:, 2], s=25)

        z_scale = self._validated_z_scale()
        self.z_scale_label_var.set(f"{z_scale:.1f}x")

        # Preserve the actual X:Y bed shape and scale only the visual Z axis.
        # set_box_aspect changes drawing proportions, not any data values.
        x_span = max(float(np.ptp(xs)), 1.0)
        y_span = max(float(np.ptp(ys)), 1.0)
        xy_max = max(x_span, y_span)
        self.ax3d.set_box_aspect((x_span / xy_max, y_span / xy_max, 0.32 * z_scale))
        self.ax3d.view_init(elev=elev, azim=azim)

        self.ax3d.set_title(f"Measured bed surface - Z visual scale {z_scale:.1f}x")
        self.ax3d.set_xlabel("X (mm)")
        self.ax3d.set_ylabel("Y (mm)")
        self.ax3d.set_zlabel("Measured Z (mm)")
        self.canvas3d.draw_idle()
''',
    "3D scale behavior",
)

text = viewer.read_text(encoding="utf-8")
for required in [
    'self.z_scale_var = tk.DoubleVar(value=1.0)',
    'text="3D Z scale:"',
    'def _validated_z_scale(self):',
    'self.ax3d.set_box_aspect(',
    'Z visual scale',
]:
    if required not in text:
        raise SystemExit(f"3D scale regression guard missing: {required}")

print("Monster8 mesh viewer: adjustable visual Z scaling added (0.1x to 50x)")
