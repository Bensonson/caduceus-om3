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
usage: rgbpics.py [--preview PNG]     (build.py imports streams())"""
import argparse, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkicons
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'card'))
import mkguides

RED, GREEN, BLUE, WHITE, EDGE = 122, 40, 53, 10, 7   # test 2: blue 53 (105 / 125 do not show blue: camera, om-emu)


def letters(parts, w, h, cap, base, gap=1):
    """parts = [(text, fill index)] side by side, centred: fill where coverage >= 0.45, a dark edge round the ink"""
    covs = [(mkicons.word(t, cap, w, 1.0)[0], mkicons.word(t, cap, w, 1.0)[1], f) for t, f in parts]
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


LEGEND = ('Front dial: point', 'Rear dial: up / down')
LG_W, LG_H = 176, 40


def legend():
    """the dials' legend drawn into the curve picture (cv_draw, top left): 2 bits a pixel, 4 to a byte (first pixel in
    the low bits): 0 clear, 1 the dark edge, 2 white, 3 soft. -> (w, h, bytes)"""
    from scipy import ndimage
    cov = np.zeros((LG_H, LG_W))
    for k, txt in enumerate(LEGEND):
        a, b = mkicons.word(txt, 12, LG_W - 6, 0.95)
        y0 = int(round(15 + 19 * k - b))
        h, w = a.shape
        cov[y0:y0 + h, 3:3 + w] = np.maximum(cov[y0:y0 + h, 3:3 + w], a[:LG_H - y0, :LG_W - 3])
    px = np.zeros((LG_H, LG_W), dtype=np.uint8)
    fill = cov >= 0.5
    px[(cov >= 0.25) & ~fill] = 3
    px[fill] = 2
    e = ndimage.distance_transform_edt(~(cov >= 0.25))
    px[(e > 0) & (e <= 1.5)] = 1
    out = bytearray()
    for row in px:
        for x in range(0, LG_W, 4):
            out.append(int(row[x]) | int(row[x + 1]) << 2 | int(row[x + 2]) << 4 | int(row[x + 3]) << 6)
    return LG_W, LG_H, bytes(out), px


def pictures():
    """(name, palette index array) in the order of the firmware's cv_pic table"""
    return [('blank', np.zeros((2, 2), dtype=np.uint8)),
            ('R', label([('R', RED)])), ('G', label([('G', GREEN)])), ('B', label([('B', BLUE)])),
            ('Pt', label([('Pt', WHITE)])), ('guide', guide()), ('cell', cell())]


def streams():
    out = []
    for name, a in pictures():
        h, w = a.shape
        out.append((name, w, h, mkicons.encode11(bytes(a.flatten().tolist()), w, h)))   # no run past a row's end
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--preview')
    a = ap.parse_args()
    COL = {0: (40, 40, 40), 7: (0, 0, 0), 9: (30, 30, 30), 10: (254, 254, 254), 11: (170, 170, 170), 12: (85, 85, 85),
           RED: (255, 1, 1), GREEN: (0, 255, 0), BLUE: (20, 116, 248), 125: (0, 0, 254)}
    for name, w, h, s in streams():
        print(name, w, h, len(s))
    if a.preview:
        lw, lh, lb, lpx = legend()
        pics = pictures() + [('legend', np.choose(lpx, [0, 7, 10, 11]).astype(np.uint8))]
        W = sum(p.shape[1] + 10 for _, p in pics); H = max(p.shape[0] for _, p in pics)
        im = Image.new('RGB', (W, H), (40, 40, 40)); x = 0
        for _, p in pics:
            rgb = np.array([[COL.get(int(v), (255, 0, 255)) for v in row] for row in p], dtype=np.uint8)
            im.paste(Image.fromarray(rgb), (x, 0)); x += p.shape[1] + 10
        im.resize((W * 3, H * 3), Image.NEAREST).save(a.preview)
