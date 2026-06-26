"""
Campsite coordinate picker, works for any campground PNG.

Hover over a site number on the map and click to record it.
Each click asks: site number + campground name (two pieces of info read
simultaneously from the map, which is why there's no separate OCR step).

Usage:
  python scripts/pick_sites.py                                  # Quartzite/NL defaults
  python scripts/pick_sites.py --image "path/to/map.png" --campground myCamp --output campsite_maps/my_picks.json

Controls:
  Mouse       – crosshair + pixel readout in status bar
  Scroll      – zoom in/out
  Click       – record a site (prompts for number + campground)
  Right-click – undo last point
  Middle-drag – pan
  S           – save JSON
  Q / Esc     – quit (auto-saves)

When done, run:
  python scripts/_export_sites.py --picked <output_json> --gcps "Campsite Maps/overlay_gcps.json"
"""

import argparse, os, re, sys
import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import json

_HERE  = os.path.dirname(os.path.abspath(__file__))
_ROOT  = os.path.dirname(_HERE)

# ── CLI args ──────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description='Campsite coordinate picker')
ap.add_argument('--image', default=os.path.join(_ROOT, 'Campsite Maps',
                'Quartzite and Northern Lights Campground.png'),
                help='Path to campground PNG')
ap.add_argument('--output', default=os.path.join(_ROOT, 'campsite_maps', 'picked_sites.json'),
                help='Output JSON path')
ap.add_argument('--campground', default=None,
                help='Default campground slug (skips per-click prompt if provided)')
args = ap.parse_args()

IMG = args.image
OUT = args.output
DEFAULT_CG = args.campground

SITE_RE = re.compile(r'^\d{1,3}[eE]?$')
ZOOM_LEVELS = [0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]


class Picker:
    def __init__(self, root):
        self.root = root
        img_name = os.path.basename(IMG)
        root.title(f'Campsite Picker, {img_name}')
        root.geometry('1400x860')

        if not os.path.exists(IMG):
            messagebox.showerror('File not found', f'Image not found:\n{IMG}')
            sys.exit(1)

        self.img_orig = Image.open(IMG).convert('RGB')
        self.iw, self.ih = self.img_orig.size

        self.points = []
        if os.path.exists(OUT):
            try:
                with open(OUT) as f:
                    self.points = json.load(f)
                print(f'Loaded {len(self.points)} existing picks from {OUT}')
            except Exception:
                pass

        self.zoom_idx = 3
        self.pan_x = self.pan_y = 0
        self._pan_start = None
        self._tk_img = None
        self.mx = self.my = 0

        self._build_ui()
        self._render()

    def _build_ui(self):
        tb = tk.Frame(self.root, bg='#1a1a1a', pady=3)
        tb.pack(side='top', fill='x')

        tk.Label(tb, text='Zoom:', fg='#888', bg='#1a1a1a', font=('Arial', 9)).pack(side='left', padx=(6,1))
        for label, delta in [('+', 1), ('–', -1)]:
            tk.Button(tb, text=label, command=lambda d=delta: self._zoom_by(d),
                      bg='#222', fg='white', width=2, font=('Arial', 9)).pack(side='left', padx=1)

        tk.Label(tb, text='  |', fg='#444', bg='#1a1a1a').pack(side='left')
        tk.Button(tb, text='Undo last', command=self._undo,
                  bg='#3a1a1a', fg='white', font=('Arial', 9)).pack(side='left', padx=4)
        tk.Button(tb, text='Save  S', command=self._save,
                  bg='#1a3a1a', fg='white', font=('Arial', 9, 'bold')).pack(side='left', padx=4)

        self.lbl_count = tk.Label(tb, text='', fg='#9bc23c', bg='#1a1a1a', font=('Arial', 9))
        self.lbl_count.pack(side='left', padx=8)

        tk.Label(tb, text='Click=place  Right-click=undo  Scroll=zoom  Middle-drag=pan  S=save  Q=quit',
                 fg='#666', bg='#1a1a1a', font=('Arial', 8)).pack(side='right', padx=8)

        self.status = tk.Label(self.root, text='Move mouse over the map', fg='#aaa', bg='#111',
                                anchor='w', font=('Courier', 10), padx=6)
        self.status.pack(side='bottom', fill='x')

        self.canvas = tk.Canvas(self.root, bg='#0a0a0a', cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)

        self.canvas.bind('<Motion>',          self._on_motion)
        self.canvas.bind('<ButtonPress-1>',   self._on_click)
        self.canvas.bind('<ButtonPress-3>',   lambda e: self._undo())
        self.canvas.bind('<ButtonPress-2>',   lambda e: setattr(self, '_pan_start', (e.x, e.y)))
        self.canvas.bind('<B2-Motion>',       self._on_pan)
        self.canvas.bind('<MouseWheel>',      self._on_scroll)
        self.canvas.bind('<Configure>',       lambda _e: self._render())
        self.root.bind('<s>', lambda _e: self._save())
        self.root.bind('<S>', lambda _e: self._save())
        self.root.bind('<q>', lambda _e: self._quit())
        self.root.bind('<Escape>', lambda _e: self._quit())

    def _zoom(self): return ZOOM_LEVELS[self.zoom_idx]

    def _tc(self, px, py):
        z = self._zoom()
        return px*z + self.pan_x, py*z + self.pan_y

    def _ti(self, cx, cy):
        z = self._zoom()
        return (cx - self.pan_x)/z, (cy - self.pan_y)/z

    def _zoom_by(self, d):
        px, py = self._ti(self.mx, self.my)
        self.zoom_idx = max(0, min(len(ZOOM_LEVELS)-1, self.zoom_idx+d))
        z = self._zoom()
        self.pan_x = self.mx - px*z
        self.pan_y = self.my - py*z
        self._render()

    def _on_scroll(self, e):
        self._zoom_by(1 if e.delta > 0 else -1)

    def _on_pan(self, e):
        if self._pan_start:
            self.pan_x += e.x - self._pan_start[0]
            self.pan_y += e.y - self._pan_start[1]
            self._pan_start = (e.x, e.y)
            self._render()

    def _on_motion(self, e):
        self.mx, self.my = e.x, e.y
        px, py = self._ti(e.x, e.y)
        self.status.config(
            text=f'  Image pixel:  x={int(round(px)):4d}  y={int(round(py)):4d}'
                 f'      zoom {self._zoom():.2f}x      '
                 f'Points recorded: {len(self.points)}'
        )
        self._render()

    def _on_click(self, e):
        px, py = self._ti(e.x, e.y)
        if not (0 <= px < self.iw and 0 <= py < self.ih):
            return

        if DEFAULT_CG:
            # Single-campground mode: only ask for site number
            prompt = (f'Clicked pixel ({int(px)}, {int(py)})\n\n'
                      f'Campground: {DEFAULT_CG}\n'
                      'Enter site number (e.g.  3  or  7e):')
            name = simpledialog.askstring('Site number', prompt, parent=self.root)
            if not name:
                return
            parts = [name.strip()]
            cg = DEFAULT_CG
        else:
            # Multi-campground mode: ask for "7e quartzite" or "109e northern_lights"
            prompt = (f'Clicked pixel ({int(px)}, {int(py)})\n\n'
                      'Enter:  <site_number> [campground_slug]\n'
                      'Examples:  7e quartzite    109e northern_lights    3\n'
                      '(campground defaults to last used or first word in filename)')
            name = simpledialog.askstring('Site + campground', prompt, parent=self.root)
            if not name:
                return
            parts = name.strip().split()
            if len(parts) >= 2:
                cg = parts[1].lower()
            else:
                cg = getattr(self, '_last_cg', os.path.splitext(os.path.basename(IMG))[0].lower()[:20])

        site_num = parts[0].lower()
        if not SITE_RE.match(site_num):
            messagebox.showwarning('Bad format', f'"{site_num}" is not a valid site number (e.g. 7 or 7e)')
            return

        self._last_cg = cg
        stype = 'electrical' if site_num.endswith('e') else 'standard'
        self.points.append({'name': site_num, 'campground': cg,
                             'site_type': stype, 'px': round(px, 1), 'py': round(py, 1)})
        self._update_count()
        self._render()

    def _undo(self):
        if self.points:
            removed = self.points.pop()
            print(f'Removed: {removed["name"]}')
            self._update_count()
            self._render()

    def _update_count(self):
        by_cg = {}
        for p in self.points:
            by_cg[p['campground']] = by_cg.get(p['campground'], 0) + 1
        summary = '  '.join(f'{k}={v}' for k, v in sorted(by_cg.items()))
        self.lbl_count.config(text=f'Picked: {len(self.points)}  ({summary})')

    def _render(self):
        z    = self._zoom()
        rsmp = Image.Resampling.LANCZOS if z <= 1.0 else Image.Resampling.NEAREST
        w    = max(1, int(self.iw * z))
        h    = max(1, int(self.ih * z))
        img  = self.img_orig.resize((w, h), rsmp)
        draw = ImageDraw.Draw(img)

        cx_img = self.mx - self.pan_x
        cy_img = self.my - self.pan_y
        r = 12
        draw.line([(cx_img - r, cy_img), (cx_img + r, cy_img)], fill=(255,0,0), width=1)
        draw.line([(cx_img, cy_img - r), (cx_img, cy_img + r)], fill=(255,0,0), width=1)

        for p in self.points:
            cx, cy = p['px'] * z, p['py'] * z
            dot_r = max(3, int(4 * z))
            color = '#f1c40f' if p['site_type'] == 'electrical' else '#2ecc71'
            draw.ellipse([cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r],
                          fill=color, outline='white')
            if z >= 1.25:
                draw.text((cx + dot_r + 2, cy - 6), p['name'].upper(), fill='white')

        self._tk_img = ImageTk.PhotoImage(img)
        c = self.canvas
        c.delete('all')
        c.create_image(self.pan_x, self.pan_y, anchor='nw', image=self._tk_img)
        self._update_count()

    def _save(self):
        os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
        with open(OUT, 'w') as f:
            json.dump(self.points, f, indent=2)
        self.status.config(text=f'  Saved {len(self.points)} points to {OUT}')
        print(f'Saved {len(self.points)} points → {OUT}')

    def _quit(self):
        self._save()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = Picker(root)
    root.mainloop()
