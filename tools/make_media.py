"""GIF and 1080p MP4 from the per-update VRAM dumps of one pass (each
update is one 59.92 Hz frame in openMSX, see the capture log)."""
import sys, glob, re, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert import frames_geo
scene, ddir, tag, outdir = sys.argv[1:5]
frames = frames_geo(scene)
pals = [np.array([round(c * 255 / 31) for c in f['full_palette']], np.uint8).reshape(16, 3) for f in frames]
files = sorted(glob.glob(f'{ddir}/{tag}_s*_u*.vram'), key=lambda f: int(re.search(r'_u(\d+)', f).group(1)))
seq = []
seen = set()
for f in files:
    s = int(re.search(r'_s(\d+)_', f).group(1))
    if s in seen:
        break
    seen.add(s); seq.append((s, f))
def rgb(s, f):
    a = np.frombuffer(Path(f).read_bytes(), np.uint8).reshape(212, 128)
    px = np.empty((212, 256), np.uint8); px[:, 0::2] = a >> 4; px[:, 1::2] = a & 15
    return pals[s][px]
rate = 21477270 / (1368 * 262)
mp4 = f'{outdir}/niccc_1pass_1080p.mp4'
p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '256x212',
                      '-framerate', f'{rate:.6f}', '-i', '-', '-vf', 'scale=1440:1080:flags=neighbor,pad=1920:1080:240:0:black,fps=60',
                      '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', mp4],
                     stdin=subprocess.PIPE)
for s, f in seq:
    p.stdin.write(rgb(s, f).tobytes())
p.stdin.close(); p.wait()
gif = [Image.fromarray(rgb(s, f)).resize((512, 424), Image.NEAREST) for s, f in seq[0:720:2]]
gif[0].save(f'{outdir}/niccc_first12s.gif', save_all=True, append_images=gif[1:], duration=33, loop=0, optimize=True)
for s in (0, 100, 500, 1000, 1799):
    Image.fromarray(rgb(*seq[s])).resize((512, 424), Image.NEAREST).save(f'{outdir}/emu_frame_{s:04d}.png')
print(len(seq), 'frames')
