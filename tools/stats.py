"""Per-frame statistics of scene1.bin and the Geo3D mapping cost.

Geo3D mapping: each polygon -> fan of convex quads (0,i,i+1,i+2) plus a
final triangle; faces filled row by row (one LINE per row, inclusive spans
between the leftmost and rightmost edge crossing, as Geo3D does).
Vertices per frame: indexed frames use their shared vertex list;
non-indexed frames are de-duplicated by coordinate.  RUNs are packed in
stream order under 255 vertices / 255 faces.

Time model (assumptions, see report):
  fill     : per LINE  T_CMD + px * T_PX
  upload   : bytes to 9Fh * T_BYTE (R800 OTIR, no wait)
  per RUN  : RUN_OVH bytes of registers/pose
  clear    : HMMV 256x200 at T_HMMV per pixel
  palette  : 48 bytes to 9Ah at T_IO98 each (only on palette frames)
"""
import sys, csv, math
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from niccc import parse

T_PX = 0.145e-6
T_CMD = 33 / 21.47727e6
T_BYTE = (0.5e-6, 0.68e-6, 0.85e-6)
RUN_OVH = 40
T_HMMV = 0.145e-6 / 2          # HMMV writes two pixels per byte (assumed half the LINE pixel time)
T_IO98 = 3e-6
VBL = 1 / 59.92


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex(pts):
    n = len(pts)
    if n < 4:
        return True
    s = 0
    for i in range(n):
        c = cross(pts[i], pts[(i + 1) % n], pts[(i + 2) % n])
        if c == 0:
            continue
        if s == 0:
            s = 1 if c > 0 else -1
        elif (c > 0) != (s > 0):
            return False
    return True


def area2(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def fan(pts):
    """Geo3D faces: quads (0,i,i+1,i+2), last one a triangle if needed."""
    n = len(pts)
    out = []
    i = 1
    while i + 1 < n:
        if i + 2 < n:
            out.append([pts[0], pts[i], pts[i + 1], pts[i + 2]]); i += 2
        else:
            out.append([pts[0], pts[i], pts[i + 1]]); i += 1
    return out


def spans(face):
    """Rows and pixels of one face with Geo3D's rule (inclusive span between
    leftmost and rightmost edge crossing per row)."""
    ys = [p[1] for p in face]
    rows = px = 0
    n = len(face)
    for y in range(min(ys), max(ys) + 1):
        xs = []
        for k in range(n):
            (xa, ya), (xb, yb) = face[k], face[(k + 1) % n]
            if ya == yb:
                if y == ya:
                    xs += [xa, xb]
            elif min(ya, yb) <= y <= max(ya, yb):
                xs.append(xa + ((y - ya) * (xb - xa)) // (yb - ya))
        if xs:
            rows += 1
            px += max(xs) - min(xs) + 1
    return rows, px


def main(src, out_csv):
    frames = parse(src)
    rows_out = []
    concave_total = 0
    degenerate_total = 0
    for i, f in enumerate(frames):
        polys = f['polys']
        nv_hist = {}
        faces = rows = px = 0
        concave = degenerate = 0
        run_v = run_f = 0
        runs = 1
        seen = set()
        vref = 0
        for col, pts in polys:
            nv_hist[len(pts)] = nv_hist.get(len(pts), 0) + 1
            vref += len(pts)
            if not convex(pts):
                concave += 1
            if area2(pts) == 0:
                degenerate += 1
            fs = fan(pts)
            nvu = len(set(pts) - seen) if not f['indexed'] else len(set(pts) - seen)
            if run_v + nvu > 255 or run_f + len(fs) > 255:
                runs += 1; run_v = run_f = 0; seen = set(); nvu = len(set(pts))
            seen |= set(pts); run_v += nvu; run_f += len(fs)
            faces += len(fs)
            for fc in fs:
                r, p_ = spans(fc)
                rows += r; px += p_
        concave_total += concave; degenerate_total += degenerate
        verts = f.get('nverts_indexed') if f['indexed'] else len(set(p for _, pts in polys for p in pts))
        upload = 6 * verts + 11 * faces + RUN_OVH * runs
        fill = rows * T_CMD + px * T_PX
        t = {k: fill + upload * tb + (256 * 200 * T_HMMV if f['clear'] else 0) + (48 * T_IO98 if f['pal_changes'] else 0)
             for k, tb in zip(('fast', 'mid', 'slow'), T_BYTE)}
        rows_out.append(dict(frame=i, clear=int(f['clear']), indexed=int(f['indexed']), pal_changes=f['pal_changes'],
                             polys=len(polys), vertex_refs=vref, vertices=verts, faces=faces, runs=runs,
                             rows=rows, pixels=px, concave=concave, degenerate=degenerate, upload_bytes=upload,
                             stream_bytes=f['size'],
                             t_fill_ms=round(fill * 1e3, 3), t_mid_ms=round(t['mid'] * 1e3, 3),
                             t_fast_ms=round(t['fast'] * 1e3, 3), t_slow_ms=round(t['slow'] * 1e3, 3),
                             vblanks_mid=max(1, math.ceil(t['mid'] / VBL)),
                             **{f'n{k}': nv_hist.get(k, 0) for k in range(3, 16)}))
    with open(out_csv, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)
    A = lambda k: np.array([r[k] for r in rows_out], float)
    def q(k):
        a = A(k); return f'{k}: median {np.median(a):.0f}, p90 {np.percentile(a, 90):.0f}, max {a.max():.0f}'
    for k in ('polys', 'vertices', 'faces', 'runs', 'rows', 'pixels', 'upload_bytes', 'stream_bytes'):
        print(q(k))
    print('frames', len(rows_out), 'clear', int(A('clear').sum()), 'indexed', int(A('indexed').sum()),
          'palette frames', int((A('pal_changes') > 0).sum()))
    tot = {k: int(A(f'n{k}').sum()) for k in range(3, 16)}
    print('polygons by vertex count', {k: v for k, v in tot.items() if v})
    print('concave polygons', concave_total, 'zero-area polygons', degenerate_total)
    for k in ('fast', 'mid', 'slow'):
        t = A(f't_{k}_ms')
        vb = np.maximum(1, np.ceil(t / (VBL * 1e3)))
        fps = 59.92 / vb
        print(f'time {k}: median {np.median(t):.1f} ms, p90 {np.percentile(t, 90):.1f}, max {t.max():.1f};'
              f' fps median {np.median(fps):.1f}, p10 {np.percentile(fps, 10):.1f};'
              f' whole stream {vb.sum() / 59.92:.1f} s')
    tf = A('t_fill_ms')
    print(f'fill only: median {np.median(tf):.1f} ms, max {tf.max():.1f}')
    return rows_out


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
