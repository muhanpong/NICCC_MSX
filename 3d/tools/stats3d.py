"""Per-frame Geo3D load of the 3D version over all 1800 frames: faces drawn, LINE
spans (one V9968 command per face row), pixels, patch faces/vertices, uncovered
area (clear needed, bounding box) -> csv + a cost estimate with the NICCC_MSX model
calibrated on the board (real cost ~0.77 x model)."""
import sys, csv, math, os
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_ref as R
from scene3d import load, Camera, frame_scene

T_PX = 0.145e-6; T_CMD = 33 / 21.47727e6; T_BYTE = 0.68e-6; T_HMMV_B = 0.145e-6 / 2; C = 0.77; V = 16.6834e-3

def main(out_csv):
    models, cams, rl = load(); cam = Camera(cams)
    rows = []
    for f in range(1800):
        scene = frame_scene(models, cams, rl, f, cam)
        st = dict(skip=0, patch=0, pverts=0, cull=0, draw=0, tsat=0)
        spans = px = 0
        cover = np.zeros((R.H, R.W), bool)
        orig = R.rowspans
        def rs(p, _o=orig):
            nonlocal spans, px
            d = _o(p)
            for y, (a, b) in d.items():
                if a <= b:
                    spans += 1; px += b - a + 1; cover[y, a:b + 1] = True
            return d
        R.rowspans = rs
        R.render_geo3d(scene, st)
        R.rowspans = orig
        u = ~cover
        bbox = 0
        if u.any():
            ys = np.where(u.any(1))[0]; xs = np.where(u.any(0))[0]
            bbox = (ys[-1] - ys[0] + 1) * (xs[-1] - xs[0] + 1)
        nmod = len(scene)
        upload = nmod * 24 + st['pverts'] * 6 + st['patch'] * 12 + nmod * 16   # pose + patches + per-RUN registers
        t = C * (spans * T_CMD + px * T_PX + bbox * T_HMMV_B * 2) + upload * T_BYTE   # G7: 1 byte per pixel
        rows.append(dict(frame=f, models=nmod, draw=st['draw'], skip=st['skip'], patch=st['patch'], pverts=st['pverts'],
                         spans=spans, pixels=px, uncovered=int(u.sum()), clear_bbox=int(bbox), upload=upload, t_ms=round(t * 1e3, 3)))
    with open(out_csv, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    ts = [r['t_ms'] for r in rows]
    vs = sum(max(1, math.ceil(t / (V * 1e3))) for t in ts)
    print(f"frames {len(rows)}; t median {np.median(ts):.2f} ms, p99 {np.percentile(ts,99):.2f}, max {max(ts):.2f}; "
          f"2-vsync frames {sum(t > V*1e3 for t in ts)}; fps {59.94*1800/vs:.1f}")
    for k in ('draw', 'spans', 'pixels', 'patch', 'pverts', 'upload', 'clear_bbox'):
        a = [r[k] for r in rows]; print(f"  {k}: median {np.median(a):.0f} max {max(a)}")

if __name__ == '__main__':
    main(sys.argv[1])
