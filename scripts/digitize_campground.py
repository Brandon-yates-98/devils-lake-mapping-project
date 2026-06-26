#!/usr/bin/env python3
"""
digitize_campground.py
Interactive tool to georeference a campground PNG map and digitize individual
campsite locations. Uses only stdlib (tkinter) + PIL + numpy.

Usage:
  .venv/Scripts/python.exe scripts/digitize_campground.py

PHASE 1, Ground Control Points (GCPs):
  Click a point whose GPS coordinates you know → enter lat/lon in the dialog.
  Repeat for at least 3 points (4+ improves accuracy).
  Click [Compute Transform] to fit the affine pixel→GPS transform.

  Good GCP candidates visible on satellite maps:
    - Road loop bends / intersections
    - Bathhouse buildings
    - Campground entrance / highway junction

PHASE 2, Site Placement:
  Click [Phase 2: Sites] then click each numbered spot on the map.
  Fill in site #, campground, and type in the dialog.
  Ctrl+Z undoes the last point in either phase.

[Save GeoJSON + SQL] writes:
  campsite_maps/quartzite_nl_sites.geojson   (visual QA)
  migrations/026_campsite_sites_data.sql     (run in Supabase SQL Editor)
"""
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

# ── paths ────────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

IMAGE_PATH  = os.path.join(_ROOT, 'Campsite Maps',
                            'Quartzite and Northern Lights Campground.png')
OUT_GEOJSON = os.path.join(_ROOT, 'campsite_maps', 'quartzite_nl_sites.geojson')
OUT_SQL     = os.path.join(_ROOT, 'migrations', '026_campsite_sites_data.sql')

SITE_TYPES = ['standard', 'electrical', 'handicapped', 'walk_in', 'group']
RESAMPLE   = Image.Resampling.LANCZOS


def sq(s):
    return str(s).replace("'", "''")


# ── dialogs ──────────────────────────────────────────────────────────────────

class GCPDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Add Ground Control Point')
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()
        self.transient(parent)
        cx = parent.winfo_rootx() + 240
        cy = parent.winfo_rooty() + 200
        self.geometry(f'+{cx}+{cy}')

    def _build(self):
        p = {'padx': 12, 'pady': 4}
        tk.Label(self,
                 text='Enter GPS coords for the landmark you just clicked:',
                 font=('Arial', 9)).grid(row=0, column=0, columnspan=2, sticky='w', **p)

        tk.Label(self, text='Latitude (decimal, e.g. 43.41234):').grid(
            row=1, column=0, sticky='e', **p)
        self.lat_e = tk.Entry(self, width=20)
        self.lat_e.grid(row=1, column=1, sticky='w', **p)
        self.lat_e.focus()

        tk.Label(self, text='Longitude (decimal, e.g. -89.72345):').grid(
            row=2, column=0, sticky='e', **p)
        self.lon_e = tk.Entry(self, width=20)
        self.lon_e.grid(row=2, column=1, sticky='w', **p)

        tk.Label(self, text='Label (optional):').grid(row=3, column=0, sticky='e', **p)
        self.lbl_e = tk.Entry(self, width=20)
        self.lbl_e.grid(row=3, column=1, sticky='w', **p)

        tk.Label(self,
                 text='Tip: right-click a known feature on the public satellite\n'
                      'map layer to read its coordinates.',
                 font=('Arial', 8), fg='gray', justify='left').grid(
            row=4, column=0, columnspan=2, sticky='w', padx=12, pady=(0, 4))

        bf = tk.Frame(self)
        bf.grid(row=5, column=0, columnspan=2, pady=8)
        tk.Button(bf, text='Add GCP', command=self._ok,
                  bg='#c0392b', fg='white', width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text='Cancel', command=self.destroy, width=8).pack(side=tk.LEFT, padx=4)
        self.bind('<Return>', lambda _: self._ok())
        self.bind('<Escape>', lambda _: self.destroy())

    def _ok(self):
        try:
            lat = float(self.lat_e.get().strip())
            lon = float(self.lon_e.get().strip())
        except ValueError:
            messagebox.showerror('Invalid', 'Enter decimal degrees (e.g. 43.41234, -89.72345).', parent=self)
            return
        self.result = (lat, lon, self.lbl_e.get().strip())
        self.destroy()


class SiteDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Add Campsite')
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()
        self.transient(parent)
        cx = parent.winfo_rootx() + 240
        cy = parent.winfo_rooty() + 200
        self.geometry(f'+{cx}+{cy}')

    def _build(self):
        p = {'padx': 12, 'pady': 4}
        tk.Label(self, text='Site #:').grid(row=0, column=0, sticky='e', **p)
        self.ref_e = tk.Entry(self, width=12)
        self.ref_e.grid(row=0, column=1, sticky='w', **p)
        self.ref_e.focus()

        tk.Label(self, text='Campground:').grid(row=1, column=0, sticky='e', **p)
        self.cg_box = ttk.Combobox(
            self, values=['Q, Quartzite', 'NL, Northern Lights'],
            state='readonly', width=20)
        self.cg_box.current(0)
        self.cg_box.grid(row=1, column=1, sticky='w', **p)

        tk.Label(self, text='Type:').grid(row=2, column=0, sticky='e', **p)
        self.st_box = ttk.Combobox(self, values=SITE_TYPES, state='readonly', width=20)
        self.st_box.current(0)
        self.st_box.grid(row=2, column=1, sticky='w', **p)

        bf = tk.Frame(self)
        bf.grid(row=3, column=0, columnspan=2, pady=8)
        tk.Button(bf, text='Add Site', command=self._ok,
                  bg='#27ae60', fg='white', width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text='Cancel', command=self.destroy, width=8).pack(side=tk.LEFT, padx=4)
        self.bind('<Return>', lambda _: self._ok())
        self.bind('<Escape>', lambda _: self.destroy())

    def _ok(self):
        ref = self.ref_e.get().strip()
        if not ref:
            messagebox.showerror('Missing', 'Enter a site number.', parent=self)
            return
        cg_key = 'Q' if self.cg_box.get().startswith('Q') else 'NL'
        self.result = (ref, cg_key, self.st_box.get())
        self.destroy()


# ── main app ─────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Campground Digitizer, Devil\'s Lake')
        self.geometry('1300x830')

        if not os.path.exists(IMAGE_PATH):
            messagebox.showerror('Image not found',
                                 f'Could not find:\n{IMAGE_PATH}')
            sys.exit(1)

        self.img_orig = Image.open(IMAGE_PATH)
        self.img_w, self.img_h = self.img_orig.size

        # View state
        self.zoom   = 1.0
        self.view_x = 0.0    # image-pixel coord of canvas top-left
        self.view_y = 0.0
        self._drag_start = None

        # Data
        self.gcps         = []   # [{px, py, lat, lon, label}]
        self.sites        = []   # [{px, py, lat, lon, ref, campground, site_type}]
        self.lon_coeffs   = None
        self.lat_coeffs   = None
        self.mode         = 'gcp'

        self._build_ui()
        self.after(60, self._fit_image)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Canvas (left)
        left = tk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(left, bg='#1a1a1a', cursor='crosshair', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<ButtonPress-1>',  self._on_click)
        self.canvas.bind('<ButtonPress-2>',  self._pan_start)
        self.canvas.bind('<B2-Motion>',      self._pan_move)
        self.canvas.bind('<ButtonPress-3>',  self._pan_start)
        self.canvas.bind('<B3-Motion>',      self._pan_move)
        self.canvas.bind('<MouseWheel>',     self._on_scroll)
        self.canvas.bind('<Configure>',      lambda _: self._redraw())
        self.bind('<Control-z>', self._undo)

        # Sidebar (right, fixed 290 px)
        side = tk.Frame(self, width=290, bg='#1e1e1e')
        side.pack(side=tk.RIGHT, fill=tk.Y)
        side.pack_propagate(False)

        S = {'bg': '#1e1e1e'}
        pad = {'padx': 10, 'pady': 3}

        # Phase toggle
        bf = tk.Frame(side, **S)
        bf.pack(fill=tk.X, padx=8, pady=(12, 4))
        self.btn_gcp  = tk.Button(bf, text='Phase 1: GCPs', width=13,
                                   command=self._set_gcp_mode,
                                   bg='#c0392b', fg='white', relief='flat', bd=0)
        self.btn_gcp.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_site = tk.Button(bf, text='Phase 2: Sites', width=13,
                                   command=self._set_site_mode,
                                   bg='#444', fg='#888', relief='flat', bd=0,
                                   state='disabled')
        self.btn_site.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(
            value='Phase 1, click 3+ known landmarks, then Compute Transform.')
        tk.Label(side, textvariable=self.status_var, wraplength=270,
                 justify='left', font=('Arial', 9), fg='#ccc', **S).pack(
            fill=tk.X, padx=10, pady=(4, 2))

        self.btn_compute = tk.Button(side, text='Compute Transform',
                                      command=self._compute_transform,
                                      bg='#2980b9', fg='white', relief='flat',
                                      bd=0, pady=5, state='disabled')
        self.btn_compute.pack(fill=tk.X, padx=10, pady=4)

        self.resid_var = tk.StringVar(value='')
        tk.Label(side, textvariable=self.resid_var, font=('Arial', 8),
                 fg='#2ecc71', **S).pack(fill=tk.X, padx=10)

        tk.Label(side, text='Ground Control Points', font=('Arial', 9, 'bold'),
                 fg='#aaa', **S).pack(fill=tk.X, **pad)
        self.gcp_lb = tk.Listbox(side, height=8, bg='#2a2a2a', fg='#eee',
                                  selectbackground='#444', font=('Courier', 8),
                                  relief='flat', bd=1)
        self.gcp_lb.pack(fill=tk.X, padx=10)

        tk.Label(side, text='Sites', font=('Arial', 9, 'bold'),
                 fg='#aaa', **S).pack(fill=tk.X, padx=10, pady=(8, 2))
        self.site_lb = tk.Listbox(side, height=14, bg='#2a2a2a', fg='#eee',
                                   selectbackground='#444', font=('Courier', 8),
                                   relief='flat', bd=1)
        self.site_lb.pack(fill=tk.X, padx=10)

        self.site_count_var = tk.StringVar(value='0 sites')
        tk.Label(side, textvariable=self.site_count_var, font=('Arial', 8),
                 fg='#888', **S).pack(fill=tk.X, padx=10)

        self.btn_save = tk.Button(side, text='Save GeoJSON + SQL',
                                   command=self._save,
                                   bg='#27ae60', fg='white', relief='flat',
                                   bd=0, pady=7, state='disabled')
        self.btn_save.pack(fill=tk.X, padx=10, pady=(10, 4))

        tk.Label(side, text='Ctrl+Z = undo last point  |  scroll = zoom\n'
                             'right/middle drag = pan',
                 font=('Arial', 8), fg='#555', **S).pack(fill=tk.X, padx=10)

    # ── view ─────────────────────────────────────────────────────────────────

    def _fit_image(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.after(60, self._fit_image)
            return
        self.zoom   = min(cw / self.img_w, ch / self.img_h) * 0.96
        self.view_x = -(cw - self.img_w * self.zoom) / (2 * self.zoom)
        self.view_y = -(ch - self.img_h * self.zoom) / (2 * self.zoom)
        self._redraw()

    def _c2i(self, cx, cy):
        """Canvas coords → image pixel coords."""
        return self.view_x + cx / self.zoom, self.view_y + cy / self.zoom

    def _i2c(self, ix, iy):
        """Image pixel coords → canvas coords."""
        return (ix - self.view_x) * self.zoom, (iy - self.view_y) * self.zoom

    def _redraw(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        x0 = max(0, int(self.view_x))
        y0 = max(0, int(self.view_y))
        x1 = min(self.img_w, int(self.view_x + cw / self.zoom) + 2)
        y1 = min(self.img_h, int(self.view_y + ch / self.zoom) + 2)
        if x1 <= x0 or y1 <= y0:
            return

        crop    = self.img_orig.crop((x0, y0, x1, y1))
        disp_w  = max(1, round((x1 - x0) * self.zoom))
        disp_h  = max(1, round((y1 - y0) * self.zoom))
        resized = crop.resize((disp_w, disp_h),
                               Image.NEAREST if self.zoom < 0.5 else RESAMPLE)

        self._tk_img = ImageTk.PhotoImage(resized)
        self.canvas.delete('all')

        off_cx = (x0 - self.view_x) * self.zoom
        off_cy = (y0 - self.view_y) * self.zoom
        self.canvas.create_image(off_cx, off_cy, anchor='nw', image=self._tk_img)

        # GCP markers: red crosshair
        for i, g in enumerate(self.gcps):
            cx, cy = self._i2c(g['px'], g['py'])
            r = 8
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                     outline='#e74c3c', width=2)
            self.canvas.create_line(cx-r, cy, cx+r, cy, fill='#e74c3c', width=2)
            self.canvas.create_line(cx, cy-r, cx, cy+r, fill='#e74c3c', width=2)
            lbl = g.get('label') or f'GCP{i+1}'
            self.canvas.create_text(cx+11, cy-11, text=lbl, fill='#e74c3c',
                                     font=('Arial', 9, 'bold'), anchor='w')

        # Site markers: filled circle with site number
        for s in self.sites:
            cx, cy = self._i2c(s['px'], s['py'])
            color = '#27ae60' if s['campground'] == 'quartzite' else '#2980b9'
            r = 9
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                     fill=color, outline='white', width=1.5)
            self.canvas.create_text(cx, cy, text=s['ref'], fill='white',
                                     font=('Arial', 8, 'bold'))

    def _on_scroll(self, event):
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        cx, cy = event.x, event.y
        ix = self.view_x + cx / self.zoom
        iy = self.view_y + cy / self.zoom
        self.zoom   = max(0.04, min(self.zoom * factor, 24.0))
        self.view_x = ix - cx / self.zoom
        self.view_y = iy - cy / self.zoom
        self._redraw()

    def _pan_start(self, event):
        self._drag_start = (event.x, event.y, self.view_x, self.view_y)

    def _pan_move(self, event):
        if not self._drag_start:
            return
        sx, sy, vx0, vy0 = self._drag_start
        self.view_x = vx0 - (event.x - sx) / self.zoom
        self.view_y = vy0 - (event.y - sy) / self.zoom
        self._redraw()

    # ── mode switching ────────────────────────────────────────────────────────

    def _set_gcp_mode(self):
        self.mode = 'gcp'
        self.btn_gcp.config(bg='#c0392b', fg='white')
        self.btn_site.config(bg='#444', fg='#888')
        self.status_var.set('Phase 1, click landmarks with known GPS coordinates.')

    def _set_site_mode(self):
        if self.lon_coeffs is None:
            messagebox.showwarning('No Transform',
                                   'Compute the affine transform first (Phase 1).', parent=self)
            return
        self.mode = 'site'
        self.btn_site.config(bg='#27ae60', fg='white')
        self.btn_gcp.config(bg='#444', fg='#888')
        self.status_var.set('Phase 2, click each campsite spot on the map.')

    # ── click / data entry ────────────────────────────────────────────────────

    def _on_click(self, event):
        px, py = self._c2i(event.x, event.y)
        if not (0 <= px < self.img_w and 0 <= py < self.img_h):
            return
        if self.mode == 'gcp':
            self._add_gcp(px, py)
        else:
            self._add_site(px, py)

    def _add_gcp(self, px, py):
        dlg = GCPDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        lat, lon, label = dlg.result
        self.gcps.append({'px': px, 'py': py, 'lat': lat, 'lon': lon, 'label': label})
        n = len(self.gcps)
        display = label or f'GCP{n}'
        self.gcp_lb.insert(tk.END, f'{display:<14} {lat:.5f}, {lon:.6f}')
        if n >= 3:
            self.btn_compute.config(state='normal')
        self._redraw()

    def _add_site(self, px, py):
        lon, lat = self._pixel_to_gps(px, py)
        dlg = SiteDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        ref, cg_key, site_type = dlg.result
        cg_full = 'quartzite' if cg_key == 'Q' else 'northern_lights'
        self.sites.append({
            'px': px, 'py': py, 'lat': lat, 'lon': lon,
            'ref': ref, 'campground': cg_full, 'site_type': site_type,
        })
        prefix = 'Q' if cg_full == 'quartzite' else 'NL'
        self.site_lb.insert(tk.END, f'{prefix}-{ref:<5} {site_type[:4]:<5} {lat:.4f},{lon:.5f}')
        self.site_count_var.set(f'{len(self.sites)} sites placed')
        self.btn_save.config(state='normal')
        self._redraw()

    def _undo(self, _event=None):
        if self.mode == 'gcp' and self.gcps:
            self.gcps.pop()
            self.gcp_lb.delete(tk.END)
            if len(self.gcps) < 3:
                self.btn_compute.config(state='disabled')
            # invalidate transform
            self.lon_coeffs = None
            self.lat_coeffs = None
            self.resid_var.set('')
            self.btn_site.config(state='disabled', bg='#444', fg='#888')
        elif self.mode == 'site' and self.sites:
            self.sites.pop()
            self.site_lb.delete(tk.END)
            self.site_count_var.set(f'{len(self.sites)} sites placed')
            if not self.sites:
                self.btn_save.config(state='disabled')
        self._redraw()

    # ── affine transform ──────────────────────────────────────────────────────

    def _compute_transform(self):
        n = len(self.gcps)
        if n < 3:
            messagebox.showwarning('Need More GCPs', 'Add at least 3 GCPs first.', parent=self)
            return

        px_arr  = [g['px']  for g in self.gcps]
        py_arr  = [g['py']  for g in self.gcps]
        lon_arr = [g['lon'] for g in self.gcps]
        lat_arr = [g['lat'] for g in self.gcps]

        A = np.column_stack([px_arr, py_arr, np.ones(n)])
        self.lon_coeffs, _, _, _ = np.linalg.lstsq(A, lon_arr, rcond=None)
        self.lat_coeffs, _, _, _ = np.linalg.lstsq(A, lat_arr, rcond=None)

        # Residuals in metres
        residuals = []
        for g in self.gcps:
            plon, plat = self._pixel_to_gps(g['px'], g['py'])
            dy = (plat - g['lat']) * 111_000
            dx = (plon - g['lon']) * 111_000 * np.cos(np.radians(g['lat']))
            residuals.append(np.hypot(dx, dy))

        mean_r = float(np.mean(residuals))
        max_r  = float(np.max(residuals))
        self.resid_var.set(f'mean {mean_r:.1f} m  max {max_r:.1f} m')

        self.btn_site.config(state='normal', bg='#27ae60', fg='white')
        quality = 'Good accuracy.' if max_r < 10 else 'Add more GCPs for higher accuracy.'
        self.status_var.set(
            f'Transform ready ({n} GCPs, max err {max_r:.1f} m). '
            f'Click "Phase 2: Sites" to start digitizing.')
        messagebox.showinfo(
            'Transform Computed',
            f'Affine transform fitted to {n} GCPs.\n'
            f'Mean residual : {mean_r:.1f} m\n'
            f'Max residual  : {max_r:.1f} m\n\n'
            f'{quality}',
            parent=self)

    def _pixel_to_gps(self, px, py):
        """Returns (lon, lat) for a pixel position using the fitted transform."""
        v = np.array([px, py, 1.0])
        return float(v @ self.lon_coeffs), float(v @ self.lat_coeffs)

    # ── save ─────────────────────────────────────────────────────────────────

    def _save(self):
        if not self.sites:
            messagebox.showwarning('No Sites', 'Place at least one site first.', parent=self)
            return

        features = []
        for s in self.sites:
            cg   = s['campground']
            pfx  = 'Q' if cg == 'quartzite' else 'NL'
            osm_id = f'campsite_site:{pfx}-{s["ref"]}'
            props  = {
                '_osm_id':    osm_id,
                'ref':        s['ref'],
                'campground': cg,
                'site_type':  s['site_type'],
                'name':       f'Site {s["ref"]}',
            }
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [round(s['lon'], 7), round(s['lat'], 7)],
                },
                'properties': props,
            })

        # GeoJSON preview
        os.makedirs(os.path.dirname(OUT_GEOJSON), exist_ok=True)
        with open(OUT_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({'type': 'FeatureCollection', 'features': features}, f, indent=2)

        # SQL migration
        rows = []
        for feat in features:
            p    = feat['properties']
            geom = json.dumps(feat['geometry'], separators=(',', ':'))
            rows.append(
                "('campsite_sites', '%s', st_setsrid(st_geomfromgeojson('%s'), 4326), '%s'::jsonb)"
                % (sq(p['name']), sq(geom), sq(json.dumps(p, separators=(',', ':'))))
            )

        sql = (
            '-- ============================================================\n'
            '-- Campsite Sites, individual site locations\n'
            '-- Generated by scripts/digitize_campground.py\n'
            '-- Run in Supabase: Dashboard → SQL Editor → New query\n'
            '-- ============================================================\n\n'
            "delete from osm_geometries where source = 'campsite_sites';\n\n"
            'insert into osm_geometries (source, name, geometry, properties) values\n'
            + ',\n'.join(rows) + ';\n\n'
            "select count(*) as sites_imported from osm_geometries where source = 'campsite_sites';\n"
        )

        os.makedirs(os.path.dirname(OUT_SQL), exist_ok=True)
        with open(OUT_SQL, 'w', encoding='utf-8') as f:
            f.write(sql)

        messagebox.showinfo(
            'Saved',
            f'Wrote {len(features)} sites to:\n\n'
            f'{os.path.abspath(OUT_GEOJSON)}\n\n'
            f'{os.path.abspath(OUT_SQL)}\n\n'
            f'Run the .sql file in Supabase SQL Editor to import.',
            parent=self)


if __name__ == '__main__':
    app = App()
    app.mainloop()
