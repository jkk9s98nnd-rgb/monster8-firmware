import csv
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


APP_TITLE = "Monster8 Bed Mesh Viewer"


def parse_mesh_file(path):
    """Read Monster8 V11 CSV and return metadata plus points in millimeters."""
    metadata = {}
    points = []
    in_points = False

    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            row = [item.strip() for item in row]
            if row[:3] == ["X_UM", "Y_UM", "Z_UM"]:
                in_points = True
                continue
            if in_points:
                if len(row) < 3:
                    continue
                try:
                    x_um, y_um, z_um = (int(row[0]), int(row[1]), int(row[2]))
                except ValueError:
                    continue
                points.append((x_um / 1000.0, y_um / 1000.0, z_um / 1000.0))
            elif len(row) >= 2:
                key, value = row[0], row[1]
                if key == "MONSTER8_MESH":
                    metadata["version"] = value
                else:
                    try:
                        metadata[key] = int(value)
                    except ValueError:
                        metadata[key] = value

    if not points:
        raise ValueError("No X_UM,Y_UM,Z_UM mesh points were found in this file.")

    pts = np.asarray(points, dtype=float)
    return metadata, pts


def analyze_mesh(points):
    """Fit the best plane to all probe points and calculate warp / tilt metrics."""
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]

    design = np.column_stack((x, y, np.ones_like(x)))
    coeff, _, _, _ = np.linalg.lstsq(design, z, rcond=None)
    a, b, c = coeff
    fitted = design @ coeff
    residual = z - fitted

    x_min, x_max = float(np.min(x)), float(np.max(x))
    y_min, y_max = float(np.min(y)), float(np.max(y))
    corners_xy = {
        "Front Left": (x_min, y_min),
        "Front Right": (x_max, y_min),
        "Rear Left": (x_min, y_max),
        "Rear Right": (x_max, y_max),
    }
    corners_z = {
        name: a * cx + b * cy + c for name, (cx, cy) in corners_xy.items()
    }

    return {
        "coeff": coeff,
        "fitted": fitted,
        "residual": residual,
        "corners_xy": corners_xy,
        "corners_z": corners_z,
        "z_min": float(np.min(z)),
        "z_max": float(np.max(z)),
        "z_range": float(np.ptp(z)),
        "tilt_range": float(max(corners_z.values()) - min(corners_z.values())),
        "warp_rms": float(math.sqrt(np.mean(residual ** 2))),
        "warp_range": float(np.ptp(residual)),
        "x_span": x_max - x_min,
        "y_span": y_max - y_min,
        "x_angle_deg": math.degrees(math.atan(a)),
        "y_angle_deg": math.degrees(math.atan(b)),
    }


def grid_from_points(points):
    xs = np.unique(points[:, 0])
    ys = np.unique(points[:, 1])
    xs.sort()
    ys.sort()
    zgrid = np.full((len(ys), len(xs)), np.nan)
    x_index = {float(v): i for i, v in enumerate(xs)}
    y_index = {float(v): i for i, v in enumerate(ys)}
    for x, y, z in points:
        zgrid[y_index[float(y)], x_index[float(x)]] = z
    return xs, ys, zgrid


class MeshViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x790")
        self.minsize(960, 680)

        self.file_path = None
        self.metadata = {}
        self.points = None
        self.analysis = None

        self.pitch_var = tk.StringVar(value="1.00")
        self.cw_raises_var = tk.BooleanVar(value=True)
        self.reference_var = tk.StringVar(value="Balanced (minimum movement)")
        self.file_var = tk.StringVar(value="No mesh loaded")
        self.status_var = tk.StringVar(value="Open a MESH####.CSV file from the Monster8 SD card.")

        self._build_ui()

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.after(100, lambda: self.load_mesh(sys.argv[1]))

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)
        ttk.Button(top, text="Open Mesh CSV", command=self.open_mesh).pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.file_var, padding=(12, 0)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.tab_summary = ttk.Frame(self.notebook)
        self.tab_3d = ttk.Frame(self.notebook)
        self.tab_heat = ttk.Frame(self.notebook)
        self.tab_corners = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_summary, text="Summary")
        self.notebook.add(self.tab_3d, text="3D Bed")
        self.notebook.add(self.tab_heat, text="Height Map")
        self.notebook.add(self.tab_corners, text="Corner Adjustments")

        self._build_summary_tab()
        self._build_3d_tab()
        self._build_heat_tab()
        self._build_corner_tab()

        status = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_summary_tab(self):
        outer = ttk.Frame(self.tab_summary, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        self.summary_title = ttk.Label(outer, text="No mesh loaded", font=("Segoe UI", 18, "bold"))
        self.summary_title.pack(anchor=tk.W, pady=(0, 12))

        self.summary_text = tk.Text(outer, height=22, wrap=tk.WORD, font=("Consolas", 11))
        self.summary_text.pack(fill=tk.BOTH, expand=True)
        self.summary_text.configure(state=tk.DISABLED)

    def _build_3d_tab(self):
        self.fig3d = Figure(figsize=(8, 6), dpi=100)
        self.ax3d = self.fig3d.add_subplot(111, projection="3d")
        self.canvas3d = FigureCanvasTkAgg(self.fig3d, master=self.tab_3d)
        self.canvas3d.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas3d, self.tab_3d, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)

    def _build_heat_tab(self):
        self.fig_heat = Figure(figsize=(8, 6), dpi=100)
        self.ax_heat = self.fig_heat.add_subplot(111)
        self.canvas_heat = FigureCanvasTkAgg(self.fig_heat, master=self.tab_heat)
        self.canvas_heat.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas_heat, self.tab_heat, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)

    def _build_corner_tab(self):
        controls = ttk.Frame(self.tab_corners, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Adjustment reference:").pack(side=tk.LEFT)
        ref = ttk.Combobox(
            controls,
            textvariable=self.reference_var,
            state="readonly",
            width=27,
            values=("Balanced (minimum movement)", "Front-left fixed"),
        )
        ref.pack(side=tk.LEFT, padx=(6, 18))
        ref.bind("<<ComboboxSelected>>", lambda _e: self.refresh_corner_table())

        ttk.Label(controls, text="Screw pitch mm/turn:").pack(side=tk.LEFT)
        pitch = ttk.Entry(controls, textvariable=self.pitch_var, width=7)
        pitch.pack(side=tk.LEFT, padx=(6, 18))
        pitch.bind("<KeyRelease>", lambda _e: self.refresh_corner_table())

        cw = ttk.Checkbutton(
            controls,
            text="Clockwise raises corner",
            variable=self.cw_raises_var,
            command=self.refresh_corner_table,
        )
        cw.pack(side=tk.LEFT)

        note = ttk.Label(
            self.tab_corners,
            text=(
                "Positive correction = raise that table corner; negative correction = lower it. "
                "Set the actual screw pitch before using the turn amounts."
            ),
            padding=(12, 4),
        )
        note.pack(fill=tk.X)

        self.corner_tree = ttk.Treeview(
            self.tab_corners,
            columns=("height", "move", "action", "turns", "direction"),
            show="headings",
            height=8,
        )
        headings = {
            "height": "Fitted Height",
            "move": "Move",
            "action": "Action",
            "turns": "Turns",
            "direction": "Screw Direction",
        }
        widths = {"height": 130, "move": 120, "action": 150, "turns": 100, "direction": 150}
        for col in self.corner_tree["columns"]:
            self.corner_tree.heading(col, text=headings[col])
            self.corner_tree.column(col, width=widths[col], anchor=tk.CENTER)
        self.corner_tree.pack(fill=tk.X, padx=12, pady=8)

        self.corner_explain = tk.Text(self.tab_corners, height=14, wrap=tk.WORD, font=("Segoe UI", 10))
        self.corner_explain.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.corner_explain.configure(state=tk.DISABLED)

    def open_mesh(self):
        path = filedialog.askopenfilename(
            title="Open Monster8 mesh",
            filetypes=[("Monster8 mesh CSV", "MESH*.CSV"), ("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.load_mesh(path)

    def load_mesh(self, path):
        try:
            metadata, points = parse_mesh_file(path)
            analysis = analyze_mesh(points)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the mesh file.\n\n{exc}")
            return

        self.file_path = path
        self.metadata = metadata
        self.points = points
        self.analysis = analysis
        self.file_var.set(os.path.basename(path))
        self.status_var.set(f"Loaded {len(points)} probe points from {os.path.basename(path)}")
        self.refresh_all()

    def refresh_all(self):
        self.refresh_summary()
        self.refresh_3d()
        self.refresh_heat()
        self.refresh_corner_table()

    def refresh_summary(self):
        if self.analysis is None:
            return
        a = self.analysis
        grid = self.metadata.get("GRID_POINTS", int(round(math.sqrt(len(self.points)))))
        text = (
            f"Mesh file:              {os.path.basename(self.file_path)}\n"
            f"Probe grid:             {grid} x {grid} ({len(self.points)} measured points)\n"
            f"Measured X span:        {a['x_span']:.3f} mm\n"
            f"Measured Y span:        {a['y_span']:.3f} mm\n\n"
            f"Lowest measured point:  {a['z_min']:+.3f} mm\n"
            f"Highest measured point: {a['z_max']:+.3f} mm\n"
            f"Total measured range:   {a['z_range']:.3f} mm\n\n"
            f"Best-fit table tilt:    {a['tilt_range']:.3f} mm corner-to-corner\n"
            f"X tilt angle:           {a['x_angle_deg']:+.4f} degrees\n"
            f"Y tilt angle:           {a['y_angle_deg']:+.4f} degrees\n\n"
            f"Warp after tilt removed:\n"
            f"  RMS warp:             {a['warp_rms']:.3f} mm\n"
            f"  Peak-to-peak warp:    {a['warp_range']:.3f} mm\n\n"
            "The corner adjustment page uses ALL measured probe points to fit the table plane.\n"
            "Tilt is what the corner screws can correct. Residual warp is local bed shape that corner adjustment cannot remove.\n"
        )
        self.summary_title.configure(text=f"Monster8 Mesh — {os.path.basename(self.file_path)}")
        self._set_text(self.summary_text, text)

    def refresh_3d(self):
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

    def refresh_heat(self):
        self.ax_heat.clear()
        if self.points is None:
            self.canvas_heat.draw_idle()
            return
        xs, ys, zg = grid_from_points(self.points)
        mesh = self.ax_heat.pcolormesh(xs, ys, zg, shading="nearest")
        if hasattr(self, "heat_cbar") and self.heat_cbar is not None:
            try:
                self.heat_cbar.remove()
            except Exception:
                pass
        self.heat_cbar = self.fig_heat.colorbar(mesh, ax=self.ax_heat, label="Measured Z (mm)")
        for x, y, z in self.points:
            self.ax_heat.text(x, y, f"{z:+.3f}", ha="center", va="center", fontsize=8)
        self.ax_heat.set_title("Top-down height map")
        self.ax_heat.set_xlabel("X (mm)")
        self.ax_heat.set_ylabel("Y (mm)")
        self.ax_heat.set_aspect("equal", adjustable="box")
        self.canvas_heat.draw_idle()

    def _corner_corrections(self):
        corners = self.analysis["corners_z"]
        if self.reference_var.get().startswith("Front-left"):
            target = corners["Front Left"]
        else:
            target = float(np.mean(list(corners.values())))
        return {name: target - z for name, z in corners.items()}

    def refresh_corner_table(self):
        for item in self.corner_tree.get_children():
            self.corner_tree.delete(item)
        if self.analysis is None:
            return

        corrections = self._corner_corrections()
        try:
            pitch = float(self.pitch_var.get())
            if pitch <= 0:
                pitch = None
        except ValueError:
            pitch = None

        cw_raises = self.cw_raises_var.get()
        corners = self.analysis["corners_z"]

        for name in ("Front Left", "Front Right", "Rear Left", "Rear Right"):
            move = corrections[name]
            if abs(move) < 0.005:
                action = "LEAVE"
                direction = "—"
            elif move > 0:
                action = "RAISE ↑"
                direction = "CW" if cw_raises else "CCW"
            else:
                action = "LOWER ↓"
                direction = "CCW" if cw_raises else "CW"

            turns = "—" if pitch is None or abs(move) < 0.005 else f"{abs(move) / pitch:.2f}"
            self.corner_tree.insert(
                "",
                tk.END,
                values=(f"{corners[name]:+.3f} mm", f"{move:+.3f} mm", action, turns, direction),
                text=name,
            )
            last = self.corner_tree.get_children()[-1]
            self.corner_tree.item(last, tags=(name,))

        # Treeview with headings normally hides the item text, so prepend the corner name
        self.corner_tree.configure(show="tree headings")
        self.corner_tree.heading("#0", text="Corner")
        self.corner_tree.column("#0", width=140, anchor=tk.W)

        lines = [
            f"Best-fit table tilt: {self.analysis['tilt_range']:.3f} mm.",
            f"Residual peak-to-peak warp after removing tilt: {self.analysis['warp_range']:.3f} mm.",
            "",
        ]
        if self.reference_var.get().startswith("Front-left"):
            lines.append("Reference mode: Front Left stays fixed; the other three corners are adjusted relative to it.")
        else:
            lines.append("Reference mode: Balanced; corrections are centered around zero to minimize how far the four corners need to move.")

        if pitch is None:
            lines.append("Enter your actual adjustment-screw pitch in mm per full turn to calculate screw turns.")
        else:
            lines.append(f"Using screw pitch: {pitch:.3f} mm per full turn.")
            lines.append("Screw directions follow the 'Clockwise raises corner' checkbox above.")

        lines += [
            "",
            "After making these adjustments, run bed leveling again and open the new MESH####.CSV file. "
            "The next mesh will show the remaining tilt and warp.",
        ]
        self._set_text(self.corner_explain, "\n".join(lines))

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)


if __name__ == "__main__":
    app = MeshViewer()
    app.mainloop()
