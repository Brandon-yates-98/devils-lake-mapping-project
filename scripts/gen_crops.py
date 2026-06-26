"""
Generate labeled grid crops at high zoom for campsite coordinate reading.
Each crop shows pixel bounds and grid every 25px (major lines every 100px).
Reading the site number AND its pixel position from a crop is one operation -
that's why there's no separate OCR pass.

Usage:
  python scripts/gen_crops.py
  python scripts/gen_crops.py --image "path/to/map.png" --out campsite_maps/crops
"""
import argparse
from PIL import Image, ImageDraw
import os

ap = argparse.ArgumentParser()
ap.add_argument('--image', default=None, help='Path to campground PNG (default: Quartzite/NL)')
ap.add_argument('--out',   default=None, help='Output directory for crops')
args = ap.parse_args()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
IMG_PATH = args.image or os.path.join(_ROOT, 'Campsite Maps', 'Quartzite and Northern Lights Campground.png')
OUT_DIR  = args.out   or os.path.join(_ROOT, 'campsite_maps', 'crops')
os.makedirs(OUT_DIR, exist_ok=True)

img = Image.open(IMG_PATH).convert('RGB')
IW, IH = img.size

# Grid spacing in original pixels
MINOR = 25
MAJOR = 100

def make_crop(name, x0, y0, x1, y1, zoom=4):
    """Crop (x0,y0)-(x1,y1) from original, scale by zoom, overlay grid."""
    crop = img.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    out_w, out_h = int(cw * zoom), int(ch * zoom)
    out = crop.resize((out_w, out_h), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(out)

    # Draw grid lines
    for gx in range(0, IW + 1, MINOR):
        if gx < x0 or gx > x1:
            continue
        cx = int((gx - x0) * zoom)
        major = (gx % MAJOR == 0)
        color = (200, 0, 0) if major else (200, 100, 100, 120)
        w = 2 if major else 1
        draw.line([(cx, 0), (cx, out_h)], fill=color, width=w)
        if major:
            draw.text((cx + 2, 2), str(gx), fill=(255, 50, 50))

    for gy in range(0, IH + 1, MINOR):
        if gy < y0 or gy > y1:
            continue
        cy = int((gy - y0) * zoom)
        major = (gy % MAJOR == 0)
        color = (0, 0, 200) if major else (100, 100, 200, 120)
        w = 2 if major else 1
        draw.line([(0, cy), (out_w, cy)], fill=color, width=w)
        if major:
            draw.text((2, cy + 2), str(gy), fill=(50, 50, 255))

    # Print bounds banner at top
    draw.rectangle([(0, 0), (out_w, 18)], fill=(0, 0, 0, 180))
    draw.text((4, 2), f'{name}  crop=({x0},{y0})-({x1},{y1})  zoom={zoom}x', fill=(255, 255, 0))

    out_path = os.path.join(OUT_DIR, f'{name}.png')
    out.save(out_path)
    print(f'  {out_path}  ({out_w}x{out_h})')
    return out_path

print(f'Image: {IW}x{IH}')

# ── QUARTZITE ─────────────────────────────────────────────────────────────────
# West road (sites 3, 7e-32 + 2e,7e-11e,13e-29e + 87e)
make_crop('qw_top',    155,  65, 230, 185, zoom=5)   # sites 3, 2e-11e top
make_crop('qw_mid',    155, 180, 235, 310, zoom=5)   # sites 13e-23e, 16-24
make_crop('qw_bot',    155, 300, 240, 420, zoom=5)   # sites 25-32, 25e-29e

# Top/outer loop (sites 68-84e, 3 is top-left corner)
make_crop('qt_wend',   155,  65, 290, 125, zoom=5)   # left side of top loop
make_crop('qt_emid',   240,  68, 460, 125, zoom=3)   # middle+east of top loop
make_crop('qt_far_e',  420,  68, 500, 145, zoom=5)   # far east top + NE link

# NE corner / inner ring top
make_crop('qne_top',   270, 100, 500, 200, zoom=4)   # inner ring top
make_crop('qne_mid',   270, 190, 500, 310, zoom=4)   # inner ring middle

# Inner ring south / outer QS section
make_crop('qi_s',      165, 290, 490, 440, zoom=3)   # south inner + outer

# ── NORTHERN LIGHTS ───────────────────────────────────────────────────────────
# Entrance area from Q
make_crop('nl_gate',   420, 100, 570, 260, zoom=4)   # NL entrance + 100-111

# NL north outer loop
make_crop('nl_n_w',    490, 130, 680, 260, zoom=4)   # 104-116 area
make_crop('nl_n_e',    640, 130, 840, 260, zoom=4)   # 116-127 area

# NL east side
make_crop('nl_e_top',  780, 200, 1000, 370, zoom=3)  # 127-145 outer east
make_crop('nl_e_bot',  780, 350, 1010, 520, zoom=3)  # 145-170 outer east

# NL south outer
make_crop('nl_s_e',    760, 490, 1020, 680, zoom=3)  # south-east outer
make_crop('nl_s_w',    490, 490, 780, 680, zoom=3)   # south-west outer

# NL inner rings
make_crop('nl_inner_n', 490, 250, 820, 430, zoom=3)  # inner ring north+mid
make_crop('nl_inner_s', 490, 420, 820, 570, zoom=3)  # inner ring south

# NL far south
make_crop('nl_far_s',  490, 620, 960, 810, zoom=3)   # far south (170s+, 190s+)

print('Done.')
