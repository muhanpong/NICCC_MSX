"""Two renderers of the 3D scene on the 256 x 200 NICCC screen, for comparison:

  ideal : floating point, polygons clipped at the GL near plane (0.04), painter's
          order by mean camera depth inside each model, models in renderList order
  geo3d : Geo3D v2 rules (rtl/video/geo3d): integer vertices (scale S), Q2.14
          matrix, SX = CX + Xc*F/Zc, SY = CY - Yc*F/Zc; a face is skipped if any
          vertex has Zc < ZNEAR or a saturated projection; back faces culled by the
          sign of the I0-I1-I2 screen area; within one RUN faces are drawn far to
          near by the sum of the four camera Z; each row is filled from its leftmost
          to its rightmost edge crossing.

  render_ref.py OUTDIR [frames a,b,c]   -> PNGs (original | ideal | geo3d) + stats
"""
import sys
import os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene3d import load, Camera, frame_scene, to_camera, hexcol

W, H = 256, 200
F, CX, CY = 100.0, 128.0, 100.0
NEAR_GL = 0.04
S = int(os.environ.get('S', '256'))            # world units -> Geo3D integer units
ZNEAR = int(os.environ.get('ZNEAR', '8'))
VIS = int(os.environ.get('VIS', '1'))   # sign of the visible faces' I0-I1-I2 area (screen y down)


def clip_near(poly, zn):
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ain, bin_ = a[2] >= zn, b[2] >= zn
        if ain:
            out.append(a)
        if ain != bin_:
            t = (zn - a[2]) / (b[2] - a[2])
            out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
    return out


def proj(p):
    return (CX + F * p[0] / p[2], CY - F * p[1] / p[2])


def render_ideal(scene):
    im = Image.new('RGB', (W, H), 0)
    d = ImageDraw.Draw(im)
    for name, m, basis in scene:
        cv = [to_camera(v, basis) for v in m['v']]
        faces = []
        for f in m['f']:
            pts = [cv[i - 1] for i in f[1:]]
            c = clip_near(pts, NEAR_GL)
            if len(c) < 3:
                continue
            sp = [proj(p) for p in c]
            area = sum(sp[i][0] * sp[(i + 1) % len(sp)][1] - sp[(i + 1) % len(sp)][0] * sp[i][1] for i in range(len(sp)))
            if area * VIS <= 0:
                continue
            faces.append((sum(p[2] for p in pts) / len(pts), f[0], sp))
        for z, col, sp in sorted(faces, key=lambda t: -t[0]):
            d.polygon(sp, fill=hexcol(col))
    return im


def q14(x):
    return max(-32768, min(32767, int(round(x * 16384))))


def geo3d_project(m, basis):
    r, u, w, eye = basis
    M = [[q14(a) for a in r], [q14(a) for a in u], [q14(a) for a in w]]
    T = [int(round(-S * sum(a * b for a, b in zip(row, eye)))) for row in (r, u, w)]
    sat = any(abs(t) > 32767 for t in T)
    out = []
    for v in m['v']:
        V = [int(round(S * c)) for c in v]
        c = [((M[k][0] * V[0] + M[k][1] * V[1] + M[k][2] * V[2]) >> 14) + T[k] for k in range(3)]
        xc, yc, zc = c
        if zc < ZNEAR:
            out.append(None)
            continue
        sx = CX + (1 if xc >= 0 else -1) * min(abs(xc) * F // zc, 32767)
        sy = CY - (1 if yc >= 0 else -1) * min(abs(yc) * F // zc, 32767)
        ovf = abs(xc) * F // zc > 32767 or abs(yc) * F // zc > 32767
        out.append(None if ovf else (int(sx), int(sy), zc))
    return out, sat


def rowspans(pts):
    ys = [p[1] for p in pts]
    n = len(pts)
    out = {}
    for y in range(max(0, min(ys)), min(H - 1, max(ys)) + 1):
        xs = []
        for k in range(n):
            (xa, ya), (xb, yb) = pts[k][:2], pts[(k + 1) % n][:2]
            if ya == yb:
                if y == ya:
                    xs += [xa, xb]
            elif min(ya, yb) <= y <= max(ya, yb):
                xs.append(xa + ((y - ya) * (xb - xa)) // (yb - ya))
        if xs:
            out[y] = (max(0, min(xs)), min(W - 1, max(xs)))
    return out


ZC = int(os.environ.get('ZC', '64'))     # patch clip plane (integer units)
PATCH = int(os.environ.get('PATCH', '1'))


def geo3d_camera(m, basis):
    r, u, w, eye = basis
    M = [[q14(a) for a in r], [q14(a) for a in u], [q14(a) for a in w]]
    T = [int(round(-S * sum(a * b for a, b in zip(row, eye)))) for row in (r, u, w)]
    out = []
    for v in m['v']:
        V = [int(round(S * c)) for c in v]
        out.append(tuple(((M[k][0] * V[0] + M[k][1] * V[1] + M[k][2] * V[2]) >> 14) + T[k] for k in range(3)))
    return out, any(abs(t) > 32767 for t in T)


def g3proj(c):
    xc, yc, zc = c
    px, py = abs(xc) * F // zc, abs(yc) * F // zc
    if px > 32767 or py > 32767:
        return None
    return (int(CX + (px if xc >= 0 else -px)), int(CY - (py if yc >= 0 else -py)), zc)


def render_geo3d(scene, stats):
    """stats: skip (faces Geo3D drops), patch (replacement faces sent per frame),
    pverts (new vertices for them), cull, draw"""
    img = np.zeros((H, W, 3), np.uint8)
    for name, m, basis in scene:
        cv, tsat = geo3d_camera(m, basis)
        stats['tsat'] += tsat
        faces = []
        for f in m['f']:
            idx = f[1:]
            cs = [cv[i - 1] for i in idx]
            p = [g3proj(c) if c[2] >= ZNEAR else None for c in cs]
            if any(q is None for q in p):
                stats['skip'] += 1
                if not PATCH or all(c[2] < ZC for c in cs):
                    continue
                clipped = clip_near([tuple(map(float, c)) for c in cs], ZC)
                if len(clipped) < 3:
                    continue
                pp = [g3proj((int(round(a)), int(round(b)), int(round(c)))) for a, b, c in clipped]
                if any(q is None for q in pp):
                    continue
                stats['patch'] += (len(pp) - 1) // 2      # quads of a fan (+ one triangle)
                stats['pverts'] += sum(1 for c in clipped if c not in cs)
                p = pp
            else:
                p = p + [p[-1]] * (4 - len(p))
            (x0, y0, _), (x1, y1, _), (x2, y2, _) = p[:3]
            if ((x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)) * VIS <= 0:
                stats['cull'] += 1
                continue
            faces.append((sum(q[2] for q in p[:4]) * 4 // len(p[:4]), f[0], p))
        for z, col, p in sorted(faces, key=lambda t: -t[0]):
            stats['draw'] += 1
            c = hexcol(col)
            for y, (a, b) in rowspans(p).items():
                if a <= b:
                    img[y, a:b + 1] = c
    return Image.fromarray(img)


def original_frames():
    # the 2D port's tools (NICCC_MSX/tools) read the original stream; NICCC_SCENE = scene1.bin
    # or an original disk image (OXYGEN.MSA / ST-NICC2.msa)
    tools = Path(__file__).resolve().parents[2] / 'tools'
    sys.path.insert(0, str(tools))
    from niccc import parse
    src = os.environ.get('NICCC_SCENE')
    if not src:
        sys.exit('set NICCC_SCENE to scene1.bin or an original Oxygene disk image')
    if src.lower().endswith(('.msa', '.st')):
        import tempfile
        from extract_stream import extract
        tmp = Path(tempfile.mkdtemp()) / 'scene1.bin'
        tmp.write_bytes(extract(src))
        src = str(tmp)
    return parse(src)


def render_original(fr):
    im = Image.new('RGB', (W, H), 0)
    d = ImageDraw.Draw(im)
    pal = [tuple(c * 17 for c in rgb) for rgb in fr['palette']]
    for col, pts in fr['polys']:
        d.polygon(pts, fill=pal[col])
    return im


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    want = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else list(range(0, 1800, 100))
    models, cams, rlist = load()
    cam = Camera(cams)
    orig = original_frames()
    stats_all = []
    prev_orig = Image.new('RGB', (W, H), 0)
    for f in range(1800):
        scene = frame_scene(models, cams, rlist, f, cam)
        if f not in want:
            continue
        st = dict(skip=0, patch=0, pverts=0, cull=0, draw=0, tsat=0)
        a = render_ideal(scene)
        b = render_geo3d(scene, st)
        o = render_original(orig[f])
        diff = (np.asarray(a).astype(int) - np.asarray(b).astype(int)).any(2).mean()
        st['diff_ideal_geo3d'] = round(float(diff) * 100, 2)
        st['diff_orig_ideal'] = round(float((np.abs(np.asarray(o).astype(int) - np.asarray(a).astype(int)).sum(2) > 96).mean()) * 100, 1)
        st['models'] = [s[0] for s in scene]
        stats_all.append((f, st))
        sheet = Image.new('RGB', (W * 3 + 8, H), (255, 255, 255))
        for k, im in enumerate((o, a, b)):
            sheet.paste(im, (k * (W + 4), 0))
        sheet.resize((sheet.width * 2, H * 2), Image.NEAREST).save(out / f'f{f:04d}.png')
    for f, st in stats_all:
        print(f, st)


if __name__ == '__main__':
    main()
