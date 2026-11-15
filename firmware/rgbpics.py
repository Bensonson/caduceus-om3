#!/usr/bin/env python3
"""Pictures for the RGB curves page (feature/rgb-curves), drawn from scratch (DejaVu Sans Condensed, a free font) in
the camera's OSD text style; no camera graphics are copied.

The page is the camera's Highlight & Shadow page in a mode of ours; its header labels, guide and our row's left cell
are on layers whose palettes have true colours (7 dark edge, 10 white, 11 / 12 soft, 122 red, 40 green, 53 blue: an
om-emu stripe test of the left column showed 105 and 125 not blue, as the owner saw on the camera in test 1);
the curves themselves are drawn by the firmware at run time (cv_draw) on the curve layer.
- 38 x 30 header labels (the size of the camera's "Sh" / "Hi"): "R", "G", "B" in their colours, "Pt".
- "Color [INFO]" guide (in place of "Mid [INFO]"), at most 160 px wide (checked in om-emu: the guide button is 180 px).
- the row's left cell (100 x 76, as our other choice rows): "RGB", each letter in its colour.
- a 2 x 2 clear picture (the camera's curve halves while our page shows).
- colour mix (the Mix page, mockup C): "Sat" and "Hue" header labels in red, green, blue; the "Mix" row cell. And
  mixtables(): the Mix page's circle tables (editor's colourmix.inc).
usage: rgbpics.py [--preview PNG]     (build.py imports streams())"""
import argparse, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkicons
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'card'))
import mkguides

RED, GREEN, BLUE, WHITE, EDGE = 122, 40, 53, 10, 7   # test 2: blue 53 (105 / 125 do not show blue: camera, om-emu)


def letters(parts, w, h, cap, base, gap=1, maxw=None, sx=1.0):
    """parts = [(text, fill index)] side by side, centred: fill where coverage >= 0.45, a dark edge round the ink"""
    covs = [(mkicons.word(t, cap, maxw or w, sx)[0], mkicons.word(t, cap, maxw or w, sx)[1], f) for t, f in parts]
    total = sum(c.shape[1] for c, _, _ in covs) + gap * (len(covs) - 1)
    x = (w - total) // 2
    px = np.zeros((h, w), dtype=np.uint8)
    ink = np.zeros((h, w), dtype=bool)
    for c, b, f in covs:
        y0 = int(round(base - b))
        for yy in range(c.shape[0]):
            for xx in range(c.shape[1]):
                Y, X = y0 + yy, x + xx
                if 0 <= Y < h and 0 <= X < w and c[yy, xx] >= 0.45:
                    px[Y, X] = f; ink[Y, X] = True
        x += c.shape[1] + gap
    from scipy import ndimage
    e = ndimage.distance_transform_edt(~ink)
    px[(e > 0) & (e <= 2.0)] = EDGE
    return px


def label(parts):
    return letters(parts, 38, 30, 23, 26)


def guide():
    g = mkguides.build('Color')                     # 175 x 50: the word right-aligned to col 102, the key at 107..172
    cols = np.nonzero(g.any(axis=0))[0]
    g = g[:, max(0, cols.min() - 2):]
    assert g.shape[1] <= 160, g.shape
    return g


def cell():
    return letters([('R', RED), ('G', GREEN), ('B', BLUE)], 100, 76, 26, 50, gap=2)


def small_label(t, fill):
    """colour mix test 2 (owner: "the words sat and hue get cut off"): the camera shows a header label in a 38 px box
    (a wider picture is cut there too, om-emu), so "Sat" / "Hue" are drawn smaller to fit it whole: ink inside 2..35"""
    a = letters([(t, fill)], 38, 30, 17, 26, maxw=30, sx=0.92)
    cols = np.nonzero(a.any(axis=0))[0]
    assert cols.min() >= 2 and cols.max() <= 35, (t, cols.min(), cols.max())
    return a


def mixcell():
    return letters([('Mix', WHITE)], 100, 76, 26, 50)


def pictures():
    """(name, palette index array) in the order of the firmware's cv_pic table"""
    return [('blank', np.zeros((2, 2), dtype=np.uint8)),
            ('R', label([('R', RED)])), ('G', label([('G', GREEN)])), ('B', label([('B', BLUE)])),
            ('Pt', label([('Pt', WHITE)])), ('guide', guide()), ('cell', cell())] + \
           [('Sat ' + n, small_label('Sat', c)) for n, c in (('R', RED), ('G', GREEN), ('B', BLUE))] + \
           [('Hue ' + n, small_label('Hue', c)) for n, c in (('R', RED), ('G', GREEN), ('B', BLUE))] + \
           [('Mix cell', mixcell())]


def streams():
    out = []
    for name, a in pictures():
        h, w = a.shape
        out.append((name, w, h, mkicons.encode11(bytes(a.flatten().tolist()), w, h)))   # no run past a row's end
    return out


MX_ANG = (-90, 30, 150)      # the Mix page: red at the top; clockwise yellow, green, cyan, blue, purple (screen y down)
MX_DEG = 5                    # degrees a hue step
MXR = 70                      # the ring's radius (editor's MXR); centre MXCX, MXCY (mix test 4: below our header)
MXCX, MXCY = 150, 182


def mixtables():
    import math
    ux = [round(1024 * math.cos(math.radians(MX_ANG[j] + MX_DEG * h))) for j in range(3) for h in range(-7, 8)]
    uy = [round(1024 * math.sin(math.radians(MX_ANG[j] + MX_DEG * h))) for j in range(3) for h in range(-7, 8)]
    ro, ri = [], []
    for dy in range(MXR + 3):
        o = (MXR + 1.5) ** 2 - dy * dy
        ro.append(int(math.floor(math.sqrt(o))) if o > 0 else 0)
        i = (MXR - 1.5) ** 2 - dy * dy
        ri.append(max(1, int(math.ceil(math.sqrt(i)))) if i > 0 else 0)
    tk = []
    for j in range(3):
        c, sn = math.cos(math.radians(MX_ANG[j])), math.sin(math.radians(MX_ANG[j]))
        tk += [round(MXCX + (MXR - 9) * c), round(MXCY + (MXR - 9) * sn), round(MXCX + (MXR + 9) * c), round(MXCY + (MXR + 9) * sn)]
    assert max(ro) < 256 and len(ux) == 45
    return [' .balign 4', 'mx_ux:', ' .short ' + ', '.join(map(str, ux)), 'mx_uy:', ' .short ' + ', '.join(map(str, uy)),
            ' .balign 4', 'mx_tk:', ' .long ' + ', '.join(map(str, tk)),
            'mx_ro:', ' .byte ' + ', '.join(map(str, ro)), 'mx_ri:', ' .byte ' + ', '.join(map(str, ri)), ' .balign 4']


# mix test 4: our own page header (the camera's header numbers, labels and dial symbols are hidden on our pages; the
# owner's camera drew them in its middle-value look). 2 bits a pixel: 0 clear, 1 dark edge, 2 the item's colour.
HD_TEXT = ['0', '1', '2', '3', '4', '5', '6', '7', '+', '\u2212', '\u00b1', 'Sat', 'Hue', 'R', 'G', 'B', 'Pt']
HD_H, HD_CAP, HD_BASE = 30, 20, 25


def _edge(px):
    from scipy import ndimage
    ink = px == 2
    e = ndimage.distance_transform_edt(~ink)
    px[(e > 0) & (e <= 2.0)] = 1
    return px


def hd_text(t):
    c, b = mkicons.word(t, HD_CAP, 200, 1.0)[:2]
    w = c.shape[1] + 4
    px = np.zeros((HD_H, w), dtype=np.uint8)
    y0 = int(round(HD_BASE - b))
    for yy in range(c.shape[0]):
        for xx in range(c.shape[1]):
            if 0 <= y0 + yy < HD_H and c[yy, xx] >= 0.45:
                px[y0 + yy, 2 + xx] = 2
    return _edge(px)


def hd_icon(bottom):
    """our own dial symbol (not the camera's picture): a half ring with teeth, open at the top (the main dial, under
    which the camera puts its left value) or at the bottom (the sub dial, right value)"""
    import math
    w, h = 36, 20
    cy = 2 if bottom else h - 3
    px = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            dx, dy = x + 0.5 - 18, y + 0.5 - cy
            if (dy < 0) if bottom else (dy > 0):
                continue
            r = math.hypot(dx, dy)
            a = math.degrees(math.atan2(dy, dx)) % 22.5
            tooth = a < 7 or a > 15.5
            if 9 <= r <= (16 if tooth else 14):
                px[y, x] = 2
    return _edge(px)


def hd_glyphs():
    """[(name, w, h, 2-bit rows packed four a byte, low pixel first)] in the editor's order: HD_TEXT, then the
    main dial's symbol, the sub dial's"""
    out = []
    for name, a in [(t, hd_text(t)) for t in HD_TEXT] + [('main dial', hd_icon(True)), ('sub dial', hd_icon(False))]:
        h, w = a.shape
        st = (w + 3) // 4
        b = bytearray(st * h)
        for y in range(h):
            for x in range(w):
                b[y * st + x // 4] |= int(a[y, x]) << (2 * (x % 4))
        out.append((name, w, h, bytes(b)))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--preview')
    a = ap.parse_args()
    COL = {0: (40, 40, 40), 7: (0, 0, 0), 9: (30, 30, 30), 10: (254, 254, 254), 11: (170, 170, 170), 12: (85, 85, 85),
           RED: (255, 1, 1), GREEN: (0, 255, 0), BLUE: (20, 116, 248), 125: (0, 0, 254)}
    for name, w, h, s in streams():
        print(name, w, h, len(s))
    if a.preview:
        pics = pictures(); W = sum(p.shape[1] + 10 for _, p in pics); H = max(p.shape[0] for _, p in pics)
        im = Image.new('RGB', (W, H), (40, 40, 40)); x = 0
        for _, p in pics:
            rgb = np.array([[COL.get(int(v), (255, 0, 255)) for v in row] for row in p], dtype=np.uint8)
            im.paste(Image.fromarray(rgb), (x, 0)); x += p.shape[1] + 10
        im.resize((W * 3, H * 3), Image.NEAREST).save(a.preview)
