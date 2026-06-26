"""
Campsite digitizer, sites pre-identified by Claude vision.

Workflow:
  1. Open the editor → Image Overlay → load the campground PNG.
  2. Drag/scale/rotate until it aligns with the satellite basemap.
  3. Click "Export for OCR ↓" in the overlay panel → saves overlay_gcps.json.
  4. Drop overlay_gcps.json into campsite_maps/ (or pass as CLI arg).
  5. Run:  .venv/Scripts/python.exe scripts/ocr_campsites.py

All ~200 campsite locations are pre-seeded from image analysis.
Review the dots, drag any that are off, right-click to edit/delete,
click "+ Add" for anything missed, then Save.

Requirements: pip install Pillow numpy
"""

import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
from PIL import Image, ImageTk
import numpy as np
import json, re, os, sys

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE       = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_HERE)
IMG_PATH    = os.path.join(_ROOT, 'Campsite Maps', 'Quartzite and Northern Lights Campground.png')
OUT_DIR     = os.path.join(_ROOT, 'campsite_maps')
OUT_GEOJSON = os.path.join(OUT_DIR, 'quartzite_nl_sites.geojson')
OUT_SQL     = os.path.join(_ROOT, 'migrations', '026_campsite_sites_data.sql')
DEFAULT_GCP = os.path.join(OUT_DIR, 'overlay_gcps.json')

M_PER_DEG_LAT = 111320
ZOOM_LEVELS   = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
SITE_RE       = re.compile(r'^\d{1,3}[eE]?$')

# ── Pre-seeded site locations (pixel coords in 1105×802 original image) ───────
# Format: (name, campground, px, py)
# Accuracy ≈ ±10–20 px; drag any that are off during review.

SITES_DATA = [
    # ══ QUARTZITE CAMPGROUND ══════════════════════════════════════════════════
    # West road, left column (west/outside of road), going south
    ("3",    "quartzite",  175,  88),
    ("5",    "quartzite",  163, 109),
    ("6",    "quartzite",  163, 122),
    ("9",    "quartzite",  163, 137),
    ("10",   "quartzite",  163, 152),
    ("12",   "quartzite",  163, 166),
    ("14",   "quartzite",  163, 181),
    ("16",   "quartzite",  163, 205),
    ("18",   "quartzite",  163, 220),
    ("19",   "quartzite",  163, 235),
    ("28",   "quartzite",  171, 372),
    ("30",   "quartzite",  172, 398),
    ("32",   "quartzite",  170, 420),
    ("34",   "quartzite",  166, 425),
    ("36",   "quartzite",  168, 464),
    # West road, middle column (east/inside of road), going south
    ("1e",   "quartzite",  213, 100),
    ("2e",   "quartzite",  205, 109),
    ("7e",   "quartzite",  205, 122),
    ("8e",   "quartzite",  205, 137),
    ("11e",  "quartzite",  205, 166),
    ("13e",  "quartzite",  205, 181),
    ("15e",  "quartzite",  205, 205),
    ("17e",  "quartzite",  205, 220),
    ("90e",  "quartzite",  192, 296),
    ("21e",  "quartzite",  192, 313),
    ("91",   "quartzite",  193, 328),
    ("23e",  "quartzite",  192, 343),
    ("25",   "quartzite",  204, 353),
    ("27",   "quartzite",  203, 376),
    ("29",   "quartzite",  202, 401),
    ("31",   "quartzite",  203, 423),
    ("33",   "quartzite",  196, 453),
    ("35",   "quartzite",  198, 482),
    ("37",   "quartzite",  196, 497),
    # West road, outer electrical spurs
    ("87e",  "quartzite",  228, 258),
    ("93e",  "quartzite",  232, 353),
    ("95e",  "quartzite",  228, 378),
    ("97e",  "quartzite",  227, 402),
    ("94e",  "quartzite",  252, 376),
    ("96e",  "quartzite",  252, 402),
    ("98e",  "quartzite",  274, 425),
    ("99e",  "quartzite",  276, 483),
    ("100e", "quartzite",  276, 495),
    # South arc going east from bottom of west road
    ("38",   "quartzite",  175, 497),
    ("40",   "quartzite",  205, 502),
    ("41e",  "quartzite",  220, 498),
    ("42e",  "quartzite",  235, 497),
    ("43",   "quartzite",  250, 492),
    ("44",   "quartzite",  265, 485),
    ("45",   "quartzite",  280, 477),
    ("46",   "quartzite",  296, 468),
    ("47e",  "quartzite",  320, 479),
    ("48",   "quartzite",  368, 473),
    ("49e",  "quartzite",  315, 458),
    ("50",   "quartzite",  370, 444),
    # Top outer loop, going east from entrance
    ("80",   "quartzite",  219,  82),
    ("79",   "quartzite",  234,  82),
    ("78e",  "quartzite",  247,  82),
    ("77e",  "quartzite",  260,  82),
    ("76e",  "quartzite",  273,  82),
    ("75",   "quartzite",  286,  82),
    ("72",   "quartzite",  302,  82),
    ("70",   "quartzite",  322,  82),
    ("68",   "quartzite",  358,  82),
    # Inner ring top, going east
    ("74",   "quartzite",  273, 115),
    ("73",   "quartzite",  289, 115),
    ("71",   "quartzite",  308, 115),
    ("69",   "quartzite",  324, 115),
    # NE corner going south
    ("67",   "quartzite",  393, 119),
    ("66",   "quartzite",  389, 146),
    ("65",   "quartzite",  388, 170),
    # Inner ring electrical spurs going south
    ("81e",  "quartzite",  313, 173),
    ("82e",  "quartzite",  307, 188),
    ("84e",  "quartzite",  298, 210),
    ("85e",  "quartzite",  292, 225),
    ("86e",  "quartzite",  286, 240),
    ("83e",  "quartzite",  281, 248),
    ("88e",  "quartzite",  283, 264),
    ("89e",  "quartzite",  279, 276),
    # Inner ring parallel tracks
    ("64e",  "quartzite",  340, 196),
    ("63e",  "quartzite",  330, 215),
    ("62e",  "quartzite",  319, 239),
    ("60e",  "quartzite",  326, 268),
    ("61e",  "quartzite",  346, 287),
    ("58e",  "quartzite",  303, 302),
    ("56e",  "quartzite",  303, 329),
    ("54e",  "quartzite",  306, 353),
    ("53e",  "quartzite",  307, 377),
    ("52e",  "quartzite",  306, 401),
    ("51e",  "quartzite",  305, 422),
    ("59e",  "quartzite",  368, 331),
    ("57e",  "quartzite",  366, 350),
    ("55e",  "quartzite",  365, 378),

    # ══ NORTHERN LIGHTS CAMPGROUND ════════════════════════════════════════════
    # NW gate area
    ("104",  "northern_lights",  475, 124),
    ("105",  "northern_lights",  490, 116),
    ("106",  "northern_lights",  516, 108),
    ("107",  "northern_lights",  497, 104),
    # North outer ring going east
    ("109e", "northern_lights",  550, 141),
    ("110e", "northern_lights",  565, 140),
    ("111",  "northern_lights",  594, 143),
    ("112",  "northern_lights",  614, 145),
    ("113",  "northern_lights",  634, 147),
    ("114",  "northern_lights",  650, 149),
    ("116",  "northern_lights",  658, 150),
    ("117e", "northern_lights",  663, 152),
    ("118",  "northern_lights",  723, 145),
    ("119e", "northern_lights",  686, 153),
    ("120e", "northern_lights",  690, 180),
    ("121",  "northern_lights",  744, 150),
    ("122",  "northern_lights",  771, 158),
    ("124",  "northern_lights",  806, 159),
    ("125",  "northern_lights",  829, 160),
    ("126e", "northern_lights",  793, 198),
    ("127",  "northern_lights",  840, 170),
    ("128e", "northern_lights",  827, 213),
    ("129",  "northern_lights",  853, 180),
    ("130e", "northern_lights",  842, 223),
    ("131e", "northern_lights",  863, 228),
    ("132",  "northern_lights",  875, 195),
    ("133",  "northern_lights",  895, 205),
    # East outer ring going south
    ("134e", "northern_lights",  933, 243),
    ("135e", "northern_lights",  957, 247),
    ("136",  "northern_lights",  985, 233),
    ("137",  "northern_lights",  990, 248),
    ("138",  "northern_lights",  990, 260),
    ("139e", "northern_lights",  988, 272),
    ("140",  "northern_lights",  984, 285),
    ("141e", "northern_lights",  978, 298),
    ("142",  "northern_lights",  970, 312),
    ("143e", "northern_lights",  950, 332),
    ("144",  "northern_lights",  938, 342),
    ("145e", "northern_lights",  925, 350),
    ("146e", "northern_lights",  910, 357),
    ("147e", "northern_lights",  895, 363),
    ("148e", "northern_lights",  879, 367),
    ("149e", "northern_lights",  862, 370),
    ("150e", "northern_lights",  845, 373),
    ("151",  "northern_lights",  828, 375),
    ("152",  "northern_lights",  812, 376),
    ("153e", "northern_lights",  796, 377),
    ("154e", "northern_lights",  780, 377),
    ("155e", "northern_lights",  766, 376),
    ("156e", "northern_lights",  752, 374),
    ("157e", "northern_lights",  738, 371),
    ("158e", "northern_lights",  724, 367),
    ("159e", "northern_lights",  710, 362),
    ("160e", "northern_lights",  697, 356),
    ("161e", "northern_lights",  684, 349),
    ("162",  "northern_lights",  672, 341),
    # East outer continuing south
    ("163",  "northern_lights",  923, 393),
    ("164",  "northern_lights",  892, 373),
    ("165",  "northern_lights",  835, 372),
    ("166",  "northern_lights",  900, 358),
    ("167",  "northern_lights",  887, 388),
    ("168e", "northern_lights",  870, 395),
    ("169",  "northern_lights",  852, 400),
    ("170e", "northern_lights",  832, 405),
    ("171e", "northern_lights",  812, 408),
    ("172",  "northern_lights",  793, 410),
    ("173e", "northern_lights",  773, 410),
    ("174e", "northern_lights",  753, 409),
    ("175e", "northern_lights",  733, 407),
    ("176e", "northern_lights",  713, 403),
    ("177e", "northern_lights",  694, 398),
    # Inner ring 190s series
    ("193e", "northern_lights",  571, 161),
    ("192e", "northern_lights",  593, 161),
    ("191e", "northern_lights",  576, 198),
    ("190e", "northern_lights",  625, 164),
    ("189e", "northern_lights",  600, 204),
    ("188e", "northern_lights",  661, 179),
    ("187e", "northern_lights",  636, 205),
    ("186e", "northern_lights",  656, 215),
    ("185e", "northern_lights",  652, 216),
    ("184e", "northern_lights",  676, 203),
    ("183e", "northern_lights",  664, 233),
    ("182e", "northern_lights",  723, 225),
    ("181",  "northern_lights",  681, 246),
    ("180e", "northern_lights",  736, 243),
    ("179e", "northern_lights",  760, 255),
    ("178e", "northern_lights",  739, 253),
    ("123e", "northern_lights",  718, 195),
    # NW inner area (195, 196, 194e, 220e)
    ("195",  "northern_lights",  513, 204),
    ("196",  "northern_lights",  513, 220),
    ("194e", "northern_lights",  545, 223),
    ("220e", "northern_lights",  548, 245),
    ("219e", "northern_lights",  565, 248),
    # Inner rings (from nl_inner_n crop)
    ("197",  "northern_lights",  507, 293),
    ("221e", "northern_lights",  545, 293),
    ("213e", "northern_lights",  622, 272),
    ("212",  "northern_lights",  613, 297),
    ("211",  "northern_lights",  648, 277),
    ("222",  "northern_lights",  523, 298),
    ("225e", "northern_lights",  561, 312),
    ("227e", "northern_lights",  590, 315),
    ("210e", "northern_lights",  663, 302),
    ("208",  "northern_lights",  707, 305),
    ("224",  "northern_lights",  548, 323),
    ("226e", "northern_lights",  555, 332),
    ("228",  "northern_lights",  593, 322),
    ("229e", "northern_lights",  605, 328),
    ("209e", "northern_lights",  682, 325),
    ("206",  "northern_lights",  717, 322),
    ("204",  "northern_lights",  740, 327),
    ("223",  "northern_lights",  554, 278),
    # Middle range (205-218e)
    ("205",  "northern_lights",  722, 272),
    ("207e", "northern_lights",  688, 282),
    ("214",  "northern_lights",  726, 328),
    ("215",  "northern_lights",  740, 318),
    ("216",  "northern_lights",  752, 308),
    ("217",  "northern_lights",  762, 298),
    ("218e", "northern_lights",  772, 288),
    # East inner (198-203 from nl_e_bot)
    ("203",  "northern_lights",  798, 355),
    ("202e", "northern_lights",  795, 368),
    ("201e", "northern_lights",  797, 375),
    ("200e", "northern_lights",  793, 392),
    ("199e", "northern_lights",  795, 412),
    ("198",  "northern_lights",  782, 428),
    # South inner ring (230-239e arc going east)
    ("230",  "northern_lights",  513, 398),
    ("232",  "northern_lights",  532, 408),
    ("233e", "northern_lights",  550, 418),
    ("234",  "northern_lights",  568, 428),
    ("235e", "northern_lights",  583, 438),
    ("236",  "northern_lights",  598, 445),
    ("237e", "northern_lights",  612, 450),
    ("238",  "northern_lights",  625, 453),
    ("239e", "northern_lights",  638, 453),
    # SE cluster (240-246 from nl_inner_s)
    ("240",  "northern_lights",  710, 457),
    ("242",  "northern_lights",  730, 468),
    ("243",  "northern_lights",  753, 433),
    ("244",  "northern_lights",  777, 457),
    ("245",  "northern_lights",  800, 423),
    ("246",  "northern_lights",  813, 425),
]


# ── Affine from 4 overlay corners ─────────────────────────────────────────────

def gcps_from_corners(corners, iw, ih):
    return [
        (0,   0,   *corners['TL']),
        (iw,  0,   *corners['TR']),
        (iw,  ih,  *corners['BR']),
        (0,   ih,  *corners['BL']),
    ]

def fit_affine(gcps):
    A    = np.column_stack([[p[0] for p in gcps], [p[1] for p in gcps], np.ones(len(gcps))])
    lons = np.array([p[2] for p in gcps])
    lats = np.array([p[3] for p in gcps])
    lc, _, _, _ = np.linalg.lstsq(A, lons, rcond=None)
    ac, _, _, _ = np.linalg.lstsq(A, lats, rcond=None)
    return lc, ac

def pixel_to_gps(px, py, lc, ac):
    v = np.array([px, py, 1.0])
    return float(v @ lc), float(v @ ac)


# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root, gcp_path, load_path=None):
        self.root     = root
        root.title('Campsite Review')
        self.img_orig = Image.open(IMG_PATH)
        self.iw, self.ih = self.img_orig.size

        self.lon_c = self.lat_c = None
        self.sites  = []          # {name, campground, site_type, px, py, deleted?}
        self.selected = None

        self.zoom_idx = 5
        self.pan_x = self.pan_y = 0
        self._pan_click = None
        self._pan_last  = None
        self._tk_img    = None
        self._mode      = 'view'  # 'site' | 'view'
        self._dragging  = None    # index being dragged

        self._build_ui()
        if load_path:
            self._load_sites_file(load_path)
        else:
            self._load_preset_sites()
        self._render()

        if gcp_path and os.path.exists(gcp_path):
            self._load_gcp_file(gcp_path)
        else:
            self.status.config(
                text='Load overlay_gcps.json (exported from editor) to enable GPS export.'
            )

    # ── Preset data ───────────────────────────────────────────────────────────

    def _load_preset_sites(self):
        for name, cg, px, py in SITES_DATA:
            stype = 'electrical' if name.lower().endswith('e') else 'standard'
            self.sites.append({'name': name, 'campground': cg,
                                'site_type': stype, 'px': px, 'py': py})
        self._update_count()

    def _load_sites_file(self, path):
        """Seed dots from an OCR/picker JSON: [{name, campground, px, py, ...}]."""
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as ex:
            messagebox.showerror('Load error', f'{path}\n{ex}')
            return self._load_preset_sites()
        for s in data:
            name = str(s['name'])
            stype = s.get('site_type') or ('electrical' if name.lower().endswith('e') else 'standard')
            self.sites.append({'name': name, 'campground': s['campground'],
                               'site_type': stype, 'px': s['px'], 'py': s['py']})
        self._update_count()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tb = tk.Frame(self.root, bg='#1a1a1a', pady=3)
        tb.pack(side='top', fill='x')

        tk.Button(tb, text='Load GCPs…', command=self._prompt_load_gcps,
                  bg='#2d2d4a', fg='white', font=('Arial', 9)).pack(side='left', padx=4, pady=2)
        self.lbl_xform = tk.Label(tb, text='No transform, GPS export disabled',
                                   fg='#e74c3c', bg='#1a1a1a', font=('Arial', 9))
        self.lbl_xform.pack(side='left', padx=4)

        tk.Label(tb, text='  |', fg='#333', bg='#1a1a1a').pack(side='left')

        self.lbl_sites = tk.Label(tb, text='', fg='#9bc23c', bg='#1a1a1a', font=('Arial', 9))
        self.lbl_sites.pack(side='left', padx=4)
        self.btn_add = tk.Button(tb, text='+ Add', command=self._toggle_add,
                  bg='#1a3a1a', fg='white', font=('Arial', 9))
        self.btn_add.pack(side='left', padx=2)

        tk.Button(tb, text='Save ▸', command=self._save,
                  bg='#4a1a00', fg='white', font=('Arial', 9, 'bold')).pack(side='right', padx=8)
        for label, delta in [('+', 1), ('–', -1)]:
            tk.Button(tb, text=label, command=lambda d=delta: self._zoom_by(d),
                      bg='#222', fg='white', width=2, font=('Arial', 9)).pack(side='right', padx=1)
        tk.Label(tb, text='Zoom:', fg='#888', bg='#1a1a1a', font=('Arial', 9)).pack(side='right')

        self.status = tk.Label(self.root, fg='#aaa', bg='#111', anchor='w',
                                font=('Arial', 9), padx=6,
                                text='Drag dots to correct positions. Right-click to edit/delete.')
        self.status.pack(side='bottom', fill='x')

        self.canvas = tk.Canvas(self.root, bg='#0d1a0d', cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>',   self._on_ldown)
        self.canvas.bind('<B1-Motion>',       self._on_lmove)
        self.canvas.bind('<ButtonRelease-1>', self._on_lup)
        self.canvas.bind('<ButtonPress-3>',   self._on_right)
        self.canvas.bind('<ButtonPress-2>',   lambda e: setattr(self, '_pan_last', (e.x, e.y)))
        self.canvas.bind('<B2-Motion>',       self._on_mid_pan)
        self.canvas.bind('<MouseWheel>',      self._on_scroll)
        self.canvas.bind('<Configure>',       lambda _e: self._render())
        self.root.bind('<Escape>',            lambda _e: self._exit_add())

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _zoom(self): return ZOOM_LEVELS[self.zoom_idx]

    def _render(self):
        z    = self._zoom()
        rsmp = Image.Resampling.LANCZOS if z <= 1.0 else Image.Resampling.NEAREST
        img  = self.img_orig.resize((max(1, int(self.iw*z)), max(1, int(self.ih*z))), rsmp)
        self._tk_img = ImageTk.PhotoImage(img)
        c = self.canvas
        c.delete('all')
        c.create_image(self.pan_x, self.pan_y, anchor='nw', image=self._tk_img)

        for i, s in enumerate(self.sites):
            if s.get('deleted'): continue
            cx, cy  = self._tc(s['px'], s['py'])
            elec    = s['site_type'] == 'electrical'
            color   = '#e74c3c' if i == self.selected else ('#f1c40f' if elec else '#2ecc71')
            r = max(3, int(4 * z))
            c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline='white', width=1,
                          tags=f'site_{i}')
            if z >= 1.0:
                c.create_text(cx, cy - r - 3, text=s['name'], fill='black',
                               font=('Arial', max(6, int(7*z)), 'bold'))

    def _tc(self, px, py):
        z = self._zoom()
        return px*z + self.pan_x, py*z + self.pan_y

    def _ti(self, cx, cy):
        z = self._zoom()
        return (cx - self.pan_x)/z, (cy - self.pan_y)/z

    def _zoom_by(self, d):
        self.zoom_idx = max(0, min(len(ZOOM_LEVELS)-1, self.zoom_idx+d))
        self._render()

    def _on_scroll(self, e):
        self._zoom_by(1 if e.delta > 0 else -1)

    def _on_mid_pan(self, e):
        if self._pan_last:
            self.pan_x += e.x - self._pan_last[0]
            self.pan_y += e.y - self._pan_last[1]
            self._pan_last = (e.x, e.y)
            self._render()

    # ── Drag to reposition ────────────────────────────────────────────────────

    def _nearest_site(self, cx, cy, thresh_px=10):
        px, py  = self._ti(cx, cy)
        thresh  = thresh_px / self._zoom()
        best_i  = None; best_d = thresh
        for i, s in enumerate(self.sites):
            if s.get('deleted'): continue
            d = ((s['px']-px)**2 + (s['py']-py)**2)**0.5
            if d < best_d:
                best_i = i; best_d = d
        return best_i

    def _on_ldown(self, e):
        if self._mode == 'site':
            self._add_site_at(e.x, e.y)
            return
        hit = self._nearest_site(e.x, e.y)
        if hit is not None:
            self._dragging = hit
            self.selected  = hit
            self._render()
        else:
            self._pan_click = (e.x, e.y)

    def _on_lmove(self, e):
        if self._dragging is not None:
            px, py = self._ti(e.x, e.y)
            self.sites[self._dragging]['px'] = px
            self.sites[self._dragging]['py'] = py
            self._render()
        elif self._pan_click:
            self.pan_x += e.x - self._pan_click[0]
            self.pan_y += e.y - self._pan_click[1]
            self._pan_click = (e.x, e.y)
            self._render()

    def _on_lup(self, _e):
        self._dragging  = None
        self._pan_click = None

    # ── Right-click context menu ──────────────────────────────────────────────

    def _on_right(self, e):
        hit = self._nearest_site(e.x, e.y)
        if hit is None: return
        self.selected = hit
        self._render()
        s = self.sites[hit]
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=f'Site {s["name"].upper()}, {s["campground"]}', state='disabled')
        menu.add_separator()
        menu.add_command(label='Edit…',  command=lambda: self._edit(hit))
        menu.add_command(label='Delete', command=lambda: self._delete(hit))
        try:    menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

    def _edit(self, idx):
        s    = self.sites[idx]
        name = simpledialog.askstring('Edit', 'Site number (e.g. 26 or 28e):',
                                       initialvalue=s['name'], parent=self.root)
        if name and SITE_RE.match(name.strip()):
            s['name']      = name.strip().lower()
            s['site_type'] = 'electrical' if s['name'].endswith('e') else 'standard'
        self.selected = None
        self._render()

    def _delete(self, idx):
        self.sites[idx]['deleted'] = True
        self.selected = None
        self._update_count()
        self._render()

    # ── Manual add ────────────────────────────────────────────────────────────

    def _toggle_add(self):
        """+ Add is a sticky mode: stays on so each click drops a new site."""
        if self._mode == 'site':
            self._exit_add()
        else:
            self._mode = 'site'
            self.btn_add.config(text='● Adding (Esc)', bg='#2e7d32', relief='sunken')
            self.status.config(text='ADD MODE: click each campsite, type its number, Enter. '
                                    'Campground is set by location. Esc / click button to stop.')

    def _exit_add(self):
        self._mode = 'view'
        self.btn_add.config(text='+ Add', bg='#1a3a1a', relief='raised')
        self.status.config(text='Drag dots to correct positions. Right-click to edit/delete.')

    def _add_site_at(self, cx, cy):
        px, py = self._ti(cx, cy)
        # Campground from position, Quartzite is west, Northern Lights east (split x≈470).
        cg     = 'quartzite' if px < 470 else 'northern_lights'
        name   = simpledialog.askstring(
            'Site number', f'Number (e.g. 26 or 28e)   [{cg}]:', parent=self.root)
        if name is None:                      # cancelled -> leave add mode
            self._exit_add(); return
        name = name.strip().lower()
        if not SITE_RE.match(name):           # bad entry -> stay in add mode, ignore click
            self.status.config(text=f'"{name}" is not a valid site number, try again.')
            return
        stype = 'electrical' if name.endswith('e') else 'standard'
        self.sites.append({'name': name, 'campground': cg, 'site_type': stype,
                            'px': px, 'py': py})
        self._update_count()
        self._render()                        # stay in 'site' mode for the next click

    # ── GCP loading ───────────────────────────────────────────────────────────

    def _prompt_load_gcps(self):
        path = filedialog.askopenfilename(
            title='Open overlay_gcps.json',
            filetypes=[('JSON','*.json'),('All files','*.*')],
            initialdir=OUT_DIR if os.path.isdir(OUT_DIR) else _ROOT,
        )
        if path: self._load_gcp_file(path)

    def _load_gcp_file(self, path):
        try:
            with open(path) as f: data = json.load(f)
            if not {'TL','TR','BR','BL'}.issubset(data):
                raise ValueError('Missing corner keys in GCP file.')
            gcps = gcps_from_corners(data, self.iw, self.ih)
            self.lon_c, self.lat_c = fit_affine(gcps)
            self.lbl_xform.config(text='Transform loaded ✓', fg='#2ecc71')
            self.status.config(
                text=f'Loaded transform from {os.path.basename(path)}. '
                     f'Drag dots to correct positions, then Save.'
            )
        except Exception as ex:
            messagebox.showerror('GCP error', str(ex))

    # ── Update count ──────────────────────────────────────────────────────────

    def _update_count(self):
        q  = sum(1 for s in self.sites if not s.get('deleted') and s['campground']=='quartzite')
        nl = sum(1 for s in self.sites if not s.get('deleted') and s['campground']=='northern_lights')
        self.lbl_sites.config(text=f'Q: {q}  NL: {nl}')

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if self.lon_c is None:
            messagebox.showerror('No transform', 'Load overlay_gcps.json first.'); return
        active = [s for s in self.sites if not s.get('deleted')]
        if not active:
            messagebox.showerror('No sites', 'Nothing to save.'); return

        features = []
        for s in active:
            lon, lat = pixel_to_gps(s['px'], s['py'], self.lon_c, self.lat_c)
            num      = re.sub(r'[eE]$', '', s['name'])
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [round(lon,7), round(lat,7)]},
                'properties': {
                    '_osm_id':    f'campsite_site:{s["campground"][0].upper()}-{s["name"]}',
                    'name':       f'Site {s["name"].upper()}',
                    'ref':        num,
                    'campground': s['campground'],
                    'site_type':  s['site_type'],
                },
            })

        os.makedirs(OUT_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(OUT_SQL), exist_ok=True)

        with open(OUT_GEOJSON, 'w') as f:
            json.dump({'type': 'FeatureCollection', 'features': features}, f, indent=2)

        def sq(v): return str(v).replace("'","''")
        rows = ['-- Auto-generated by ocr_campsites.py',
                "delete from osm_geometries where source = 'campsite_sites';", '']
        for feat in features:
            p = feat['properties']
            ln, la = feat['geometry']['coordinates']
            g = f"st_setsrid(st_makepoint({ln},{la}),4326)"
            ps = json.dumps(p).replace("'","''")
            rows.append(
                f"insert into osm_geometries (source,name,geometry,properties) values "
                f"('campsite_sites','{sq(p['name'])}',{g},'{ps}'::jsonb);"
            )
        with open(OUT_SQL, 'w') as f:
            f.write('\n'.join(rows)+'\n')

        messagebox.showinfo('Saved',
            f'{len(features)} sites saved.\n\n'
            f'GeoJSON: {OUT_GEOJSON}\n'
            f'SQL:     {OUT_SQL}\n\n'
            f'Run the SQL in Supabase SQL Editor to import.')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Review/correct campsite dots, then Save.')
    ap.add_argument('gcp', nargs='?', default=DEFAULT_GCP,
                    help='overlay_gcps.json (default: campsite_maps/overlay_gcps.json)')
    ap.add_argument('--load', default=None,
                    help='Seed dots from an OCR/picker JSON instead of hardcoded SITES_DATA')
    a = ap.parse_args()
    if not os.path.exists(IMG_PATH):
        print(f'ERROR: image not found:\n  {IMG_PATH}'); sys.exit(1)
    root = tk.Tk()
    root.geometry('1300x820')
    App(root, a.gcp, load_path=a.load)
    root.mainloop()
