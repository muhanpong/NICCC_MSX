"""Frame-by-frame render comparison: openMSX VRAM dumps vs a Python model
of the same double-buffered Geo3D drawing.

The model replays the converted stream exactly as the player does: two
SCREEN 5 pages (both cleared at boot), page toggled before each frame,
HMMV of rows 6..205 on clear frames, then every face in stream order with
Geo3D's rules (cull when the I0-I1-I2 screen area <= 0, row spans between
the leftmost and rightmost edge crossings, inclusive, colour = BASE).

  verify_render.py SCENE DUMPDIR TAG

Pass: every dumped frame matches pixel for pixel.  Negative controls: the
same comparison with (a) one face recoloured and (b) one face dropped in
one frame must report a mismatch exactly there.
Also prints the model-vs-original difference (the ST polygon filler is
approximated by PIL's polygon fill on the original polygons).
"""
import sys, glob, re
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert import frames_geo, rowspans, Y_OFF
from niccc import parse


def draw_frame(page, fr, mutate=None):
    if fr['flags'] & 1:
        page[Y_OFF:Y_OFF + 200, :] = 0
    for k, (ids, col) in enumerate(fr['faces']):
        if mutate is not None:
            r = mutate(k, col)
            if r is None:
                continue
            col = r
        pts = [(fr['verts'][i][0], fr['verts'][i][1] + Y_OFF) for i in ids]
        (x0, y0), (x1, y1), (x2, y2) = pts[:3]
        if (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0) <= 0:
            continue
        for y, (a, b) in rowspans(pts).items():
            if 0 <= y < 212:
                page[y, max(0, a):min(255, b) + 1] = col


def model(frames, mutate_frame=None, mutate=None):
    pages = [np.zeros((212, 256), np.uint8), np.zeros((212, 256), np.uint8)]
    cur = 0
    out = []
    for k, fr in enumerate(frames):
        cur ^= 1
        draw_frame(pages[cur], fr, mutate if k == mutate_frame else None)
        out.append(pages[cur].copy())
    return out


def load_dump(path):
    a = np.frombuffer(Path(path).read_bytes(), np.uint8).reshape(212, 128)
    px = np.empty((212, 256), np.uint8); px[:, 0::2] = a >> 4; px[:, 1::2] = a & 15
    return px


def compare(ref, dumps):
    bad = {}
    for s, f in dumps.items():
        d = int((load_dump(f) != ref[s]).sum())
        if d:
            bad[s] = d
    return bad


def main(scene, ddir, tag):
    frames = frames_geo(scene)
    dumps = {}
    # first display of each stream frame after boot (update counter >= 1)
    for f in sorted(glob.glob(f'{ddir}/{tag}_s*_u*.vram'), key=lambda f: int(re.search(r'_u(\d+)', f).group(1))):
        s = int(re.search(r'_s(\d+)_', f).group(1))
        dumps.setdefault(s, f)
    ref = model(frames)
    bad = compare(ref, dumps)
    fails = 0
    ok = not bad and len(dumps) == len(frames)
    print(f"{'PASS' if ok else 'FAIL'}  emulator vs model: {len(dumps)} of {len(frames)} frames dumped, "
          f"{len(bad)} differ" + (f", worst {max(bad.items(), key=lambda t: t[1])}" if bad else ''))
    fails += not ok
    # negative controls on frame 100: the last face that shows on screen
    k0 = 100
    probe = model(frames[:k0 + 1])[k0]
    vis = None
    for k in range(len(frames[k0]['faces']) - 1, -1, -1):
        alt = model(frames[:k0 + 1], k0, lambda i, c, k=k: None if i == k else c)[k0]
        if (alt != probe).any():
            vis = k; break
    for name, mut in (('one face recoloured', lambda i, c: (c + 1) & 15 if i == vis else c),
                      ('one face dropped', lambda i, c: None if i == vis else c)):
        ref2 = model(frames[:k0 + 3], k0, mut)
        b2 = compare(ref2, {s: f for s, f in dumps.items() if s <= k0 + 2})
        hit = k0 in b2
        print(f"{'NEG-CONTROL ok' if hit else 'NEG-CONTROL BROKEN'}  {name} (frame {k0}, face {vis}): mismatch at {sorted(b2)} {b2.get(k0)} px")
        fails += not hit
    # fidelity: model vs the original polygons filled sequentially (PIL)
    seq = Image.new('L', (256, 200), 0)
    diffs = []
    for k, f in enumerate(parse(scene)):
        dr = ImageDraw.Draw(seq)
        if f['clear']:
            dr.rectangle([0, 0, 255, 199], fill=0)
        for col, pts in f['polys']:
            dr.polygon(pts, fill=col)
        diffs.append(int((np.asarray(seq) != ref[k][Y_OFF:Y_OFF + 200]).sum()))
    d = np.array(diffs)
    print(f'info: model vs original (PIL fill of the ST polygons): median {np.median(d):.0f} px, '
          f'p90 {np.percentile(d, 90):.0f}, max {d.max()} of 51200 per frame')
    # model vs the original polygons with the SAME row-span rule, unsplit,
    # sequential (no double buffer), zero-area polygons drawn: what is left
    # is the fan splitting, the zero-area culling and the double buffer
    seq = np.zeros((200, 256), np.uint8)
    d2 = []
    for k, f in enumerate(parse(scene)):
        if f['clear']:
            seq[:] = 0
        for col, pts in f['polys']:
            for y, (a, b) in rowspans(pts).items():
                seq[y, max(0, a):min(255, b) + 1] = col
        d2.append(int((seq != ref[k][Y_OFF:Y_OFF + 200]).sum()))
    d2 = np.array(d2)
    print(f'info: model vs original polygons with the same span rule: {int((d2 > 0).sum())} frames differ, '
          f'median {np.median(d2):.0f}, max {d2.max()} px; frames with > 50 px: {[int(i) for i in np.nonzero(d2 > 50)[0][:12]]}')
    print('RESULT', 'PASS' if not fails else f'FAIL ({fails})')
    return fails


if __name__ == '__main__':
    sys.exit(1 if main(*sys.argv[1:4]) else 0)
