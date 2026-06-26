"""
OCR the campground map into a picker-format sites JSON for review.

Pipeline:
  1. Tile the map into the hand-tuned crop regions (shared with gen_crops.py).
  2. Upscale + binarize each clean (no-grid) crop so Tesseract can read the
     tiny site labels.
  3. Run Tesseract, keep tokens matching the site pattern (e.g. "26", "28e").
  4. Map each token centre back to original-image pixels.
  5. Dedup across overlapping tiles, assign campground + site_type.
  6. Write campsite_maps/ocr_sites.json -> feeds scripts/ocr_campsites.py --load
     for drag-to-correct review, then Save -> migrations/026_campsite_sites_data.sql.

Usage:
  .venv/Scripts/python.exe scripts/ocr_extract_sites.py
  .venv/Scripts/python.exe scripts/ocr_extract_sites.py --min-conf 30 --scale 6
  .venv/Scripts/python.exe scripts/ocr_extract_sites.py --image "path/to/map.png"
"""
import argparse, json, os, re, sys
import numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# ── Tesseract binary location (pytesseract is only a wrapper) ──────────────────
_TESS_CANDIDATES = [
    os.environ.get('TESSERACT_CMD'),
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Tesseract-OCR', 'tesseract.exe'),
]
for _c in _TESS_CANDIDATES:
    if _c and os.path.exists(_c):
        pytesseract.pytesseract.tesseract_cmd = _c
        break

# ── Site label pattern (matches scripts/ocr_campsites.py:35) ──────────────────
SITE_RE = re.compile(r'^\d{1,3}[eE]?$')

# ── Tiling ────────────────────────────────────────────────────────────────────
# The campsite numbers live in this bounding box (loops of both campgrounds);
# below/right of it is the legend, lake, title and road labels -> excluded so
# their words don't generate digit misreads.
SITE_BBOX = (150, 60, 1020, 520)   # x0, y0, x1, y1
TILE_W, TILE_H = 110, 85           # small tiles: better local Otsu + layout
STEP_X, STEP_Y = 50, 40            # < tile size -> heavy overlap; dedup merges


def build_tiles(iw, ih, tile_w, tile_h, step_x, step_y):
    """Fine overlapping grid over the campsite bounding box."""
    bx0, by0, bx1, by1 = SITE_BBOX
    bx1, by1 = min(bx1, iw), min(by1, ih)
    tiles, row = [], 0
    y = by0
    while y < by1:
        x = bx0
        col = 0
        while x < bx1:
            tiles.append((f'r{row}c{col}', x, y, min(x + tile_w, bx1), min(y + tile_h, by1)))
            x += step_x
            col += 1
        y += step_y
        row += 1
    return tiles

# Quartzite occupies the west (low x); Northern Lights the east. The campgrounds
# are cleanly separated around x≈470, with no real sites in 440–490.
X_SPLIT = 470
# Known site-number ranges per campground (used to reject spatial misreads).
Q_RANGE  = (1, 100)
NL_RANGE = (104, 246)

# Two layout modes, 11 (sparse) and 12 (sparse + OSD), catch different
# label placements; results are merged and deduped.
TESS_PSMS = [11, 12]
TESS_CONFIG_FMT = '--oem 1 --psm {psm} -c tessedit_char_whitelist=0123456789e'


def otsu_threshold(gray: np.ndarray) -> int:
    """Compute an Otsu threshold for a uint8 grayscale array."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = gray.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0.0
    best_t, best_var = 127, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > best_var:
            best_var, best_t = var_between, t
    return best_t


def preprocess(crop: Image.Image, scale: int) -> Image.Image:
    """Upscale, grayscale, Otsu-binarize a clean crop for OCR."""
    w, h = crop.size
    big = crop.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    gray = np.asarray(big.convert('L'))
    t = otsu_threshold(gray)
    # Dark text on light background -> below threshold becomes black (0).
    binar = np.where(gray <= t, 0, 255).astype(np.uint8)
    return Image.fromarray(binar, mode='L')


def assign_campground(orig_px: float) -> str:
    """Campground from POSITION, the reliable signal (the two loops don't overlap)."""
    return 'quartzite' if orig_px < X_SPLIT else 'northern_lights'


def is_spatial_misread(num: int, orig_px: float) -> bool:
    """A Quartzite-range number floating in the NL half (or vice-versa) is a misread."""
    if num <= Q_RANGE[1] and orig_px > X_SPLIT + 20:      # 1-100 stranded in NL
        return True
    if num >= NL_RANGE[0] and orig_px < X_SPLIT - 30:     # 104-246 stranded in Quartzite
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default=os.path.join(_ROOT, 'Campsite Maps',
                    'Quartzite and Northern Lights Campground.png'))
    ap.add_argument('--out', default=os.path.join(_ROOT, 'campsite_maps', 'ocr_sites.json'))
    ap.add_argument('--scale', type=int, default=6, help='Upscale factor before OCR')
    ap.add_argument('--min-conf', type=float, default=30.0, help='Min Tesseract confidence')
    ap.add_argument('--dedup-px', type=float, default=20.0,
                    help='Merge same-label detections within this many original px')
    ap.add_argument('--tile', type=int, nargs=2, metavar=('W', 'H'), default=(TILE_W, TILE_H),
                    help='Tile size in original px (smaller = higher recall, more fragments)')
    ap.add_argument('--step', type=int, nargs=2, metavar=('X', 'Y'), default=(STEP_X, STEP_Y),
                    help='Tile step in original px (smaller = more overlap)')
    args = ap.parse_args()

    if not os.path.exists(pytesseract.pytesseract.tesseract_cmd or ''):
        # tesseract_cmd may be the bare name if found on PATH; test with a call.
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            print('ERROR: Tesseract binary not found. Set TESSERACT_CMD or install it.')
            print(f'  tried: {[c for c in _TESS_CANDIDATES if c]}')
            sys.exit(1)

    if not os.path.exists(args.image):
        print(f'ERROR: image not found: {args.image}')
        sys.exit(1)

    img = Image.open(args.image).convert('RGB')
    iw, ih = img.size
    print(f'Image: {iw}x{ih}   tesseract: {pytesseract.pytesseract.tesseract_cmd}')
    print(f'OCR scale={args.scale}x  min-conf={args.min_conf}')

    tiles = build_tiles(iw, ih, args.tile[0], args.tile[1], args.step[0], args.step[1])
    print(f'Tiles: {len(tiles)}  (bbox={SITE_BBOX}, tile={args.tile[0]}x{args.tile[1]}, '
          f'step={args.step[0]}x{args.step[1]})')

    # raw detections: list of dicts {label, px, py, conf, region}
    raw = []
    for name, x0, y0, x1, y1 in tiles:
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        crop = img.crop((x0, y0, x1, y1))
        proc = preprocess(crop, args.scale)
        for psm in TESS_PSMS:
            cfg = TESS_CONFIG_FMT.format(psm=psm)
            data = pytesseract.image_to_data(proc, output_type=Output.DICT, config=cfg)
            for i in range(len(data['text'])):
                txt = (data['text'][i] or '').strip()
                if not txt or not SITE_RE.match(txt):
                    continue
                try:
                    conf = float(data['conf'][i])
                except (ValueError, TypeError):
                    conf = -1.0
                if conf < args.min_conf:
                    continue
                # token centre in upscaled-crop space -> original-image px
                cx = data['left'][i] + data['width'][i] / 2.0
                cy = data['top'][i] + data['height'][i] / 2.0
                opx = x0 + cx / args.scale
                opy = y0 + cy / args.scale
                raw.append({'label': txt.lower(), 'px': opx, 'py': opy,
                            'conf': conf, 'region': name})

    # ── Dedup: cluster same-label detections within dedup-px; keep best conf ──
    by_label = {}
    for d in raw:
        by_label.setdefault(d['label'], []).append(d)

    sites = []
    spatial_misreads = []   # number-range contradicts pixel position -> dropped
    for label, dets in by_label.items():
        dets.sort(key=lambda d: -d['conf'])
        clusters = []  # each: representative det (highest conf so far)
        for d in dets:
            placed = False
            for c in clusters:
                if abs(c['px'] - d['px']) <= args.dedup_px and abs(c['py'] - d['py']) <= args.dedup_px:
                    placed = True
                    break
            if not placed:
                clusters.append(d)
        for c in clusters:
            num = int(re.sub(r'[eE]$', '', c['label']))
            if num < 1 or num > 250:   # 0 / 3-digit garbage from misreads
                continue
            if is_spatial_misread(num, c['px']):
                spatial_misreads.append((c['label'], round(c['px']), round(c['py'])))
                continue
            sites.append({
                'name': c['label'],
                'campground': assign_campground(c['px']),
                'site_type': 'electrical' if c['label'].endswith('e') else 'standard',
                'px': round(c['px'], 1),
                'py': round(c['py'], 1),
                'conf': round(c['conf'], 1),
            })

    # ── Suppress substring fragments: a short partial read (e.g. "1"/"14")
    #    sitting on top of a longer detection ("144") is OCR splitting one label. ──
    def digits(s): return re.sub(r'[eE]$', '', s['name'])
    frag_radius = max(args.dedup_px * 1.6, 22.0)
    keep = []
    for s in sites:
        ds = digits(s)
        shadowed = any(
            o is not s
            and len(digits(o)) > len(ds)
            and digits(o).startswith(ds)
            and abs(o['px'] - s['px']) <= frag_radius
            and abs(o['py'] - s['py']) <= frag_radius
            for o in sites
        )
        if not shadowed:
            keep.append(s)
    fragments_dropped = len(sites) - len(keep)
    sites = keep

    # Same number appearing at two+ distinct spots after suppression -> human check.
    from collections import Counter
    name_counts = Counter(s['name'] for s in sites)
    duplicates = sorted((n, c) for n, c in name_counts.items() if c > 1)

    sites.sort(key=lambda s: (s['campground'], int(re.sub(r'[eE]$', '', s['name']))))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(sites, f, indent=2)

    # ── Summary ──────────────────────────────────────────────────────────────
    q  = sum(1 for s in sites if s['campground'] == 'quartzite')
    nl = sum(1 for s in sites if s['campground'] == 'northern_lights')
    elec = sum(1 for s in sites if s['site_type'] == 'electrical')
    out_of_range = [s['name'] for s in sites
                    if not (Q_RANGE[0] <= int(re.sub(r'[eE]$', '', s['name'])) <= Q_RANGE[1]
                            or NL_RANGE[0] <= int(re.sub(r'[eE]$', '', s['name'])) <= NL_RANGE[1])]
    low_conf = sorted([s['name'] for s in sites if s['conf'] < args.min_conf + 15])

    print(f'\n{len(sites)} unique site labels  (Q={q}  NL={nl}  electrical={elec})')
    print(f'  raw detections: {len(raw)}   substring fragments dropped: {fragments_dropped}'
          f'   spatial misreads dropped: {len(spatial_misreads)}')
    if duplicates:
        print(f'  same-label multi-clusters (check these): {duplicates}')
    if out_of_range:
        print(f'  out-of-range numbers: {sorted(set(out_of_range))}')
    if low_conf:
        print(f'  low-confidence labels: {low_conf}')
    print(f'\nWrote {args.out}')
    print('Next: review with')
    print(f'  .venv/Scripts/python.exe scripts/ocr_campsites.py '
          f'"Campsite Maps/overlay_gcps.json" --load campsite_maps/ocr_sites.json')


if __name__ == '__main__':
    main()
