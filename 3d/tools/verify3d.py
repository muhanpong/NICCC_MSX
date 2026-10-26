"""Run out/stream.bin through the Geo3D/VDP model (geo3d.py) and compare the shown
page of each frame with the floating-point reference (render_ref.render_ideal,
shifted down 6 rows like the player's CY = 106).

  verify3d.py OUTDIR [every]   -> diff statistics, sample PNGs (stream | ideal)"""
import sys, os
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo3d as G, render_ref as R
from scene3d import load, Camera, frame_scene
from build3d import Builder

def main(out, every=50):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    blob = (Path(__file__).resolve().parent.parent / 'out/stream.bin').read_bytes()
    b = Builder(); pal = np.array([[c * 255 // 31 for c in rgb] for rgb in b.palette] + [[0, 0, 0]] * (256 - len(b.palette)), np.uint8)
    models, cams, rl = load(); cam = Camera(cams)
    scenes = {}
    for f in range(1800):
        sc = frame_scene(models, cams, rl, f, cam)
        if f % every == 0:
            scenes[f] = sc
    diffs = []
    def on_frame(i, vdp, geo, st):
        if i not in scenes:
            return
        img = pal[vdp.vram[256 * vdp.shown + 6:256 * vdp.shown + 206]]
        ref = np.asarray(R.render_ideal(scenes[i]))
        d = float((np.abs(img.astype(int) - ref.astype(int)).sum(2) > 48).mean() * 100)
        diffs.append((i, round(d, 2), st['draw'], st['skip']))
        s = Image.new('RGB', (516, 200), (255, 255, 255)); s.paste(Image.fromarray(img), (0, 0)); s.paste(Image.fromarray(ref), (260, 0))
        s.save(out / f'v{i:04d}.png')
    G.run_stream(blob, 0, on_frame)
    for x in diffs: print(x)
    print('mean diff % stream-vs-ideal', round(float(np.mean([d for _, d, _, _ in diffs])), 2), 'max', max(d for _, d, _, _ in diffs))

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 50)
