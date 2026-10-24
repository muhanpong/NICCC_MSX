"""Reference rasteriser: replays the stream with frame state (frames
without the clear flag draw over the previous image)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from niccc import parse
src, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
want = set(int(x) for x in sys.argv[3].split(','))
sheet_every = int(sys.argv[4]) if len(sys.argv) > 4 else 60
frames = parse(src)
im = Image.new('P', (256, 200), 0)
sheet = []
for i, f in enumerate(frames):
    pal = [c * 17 for rgb in f['palette'] for c in rgb]
    im.putpalette(pal + [0] * (768 - len(pal)))
    d = ImageDraw.Draw(im)
    if f['clear']:
        d.rectangle([0, 0, 255, 199], fill=0)
    for col, pts in f['polys']:
        d.polygon(pts, fill=col)
    if i in want:
        im.convert('RGB').resize((512, 400), Image.NEAREST).save(out / f'ref_{i:04d}.png')
    if i % sheet_every == 0:
        sheet.append(im.convert('RGB'))
cols = 6
s = Image.new('RGB', (cols * 258, ((len(sheet) + cols - 1) // cols) * 202), (255, 255, 255))
for k, t in enumerate(sheet):
    s.paste(t, ((k % cols) * 258, (k // cols) * 202))
s.save(out / 'ref_sheet.png')
