"""Build NICCC.ROM: native ASCII16X, 4 MiB.

  SDCC_BIN=... python tools/build.py SCENE1.BIN
"""
import os, sys, json, hashlib, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert import frames_geo, record, Y_OFF

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out'
TOOL = Path(os.environ.get('SDCC_BIN', '/home/linuxbrew/.linuxbrew/bin'))
ROM_SIZE = 4 << 20
FIRSTBANK = 1


def build(scene):
    OUT.mkdir(exist_ok=True)
    frames = frames_geo(scene)
    for f in frames:
        if not f['faces']:
            f['verts'] = []
    banks = [bytearray(16384)]
    cur = bytearray()
    placed = []
    for i, f in enumerate(frames):
        r = record(f)
        assert len(r) < 16383
        if len(cur) + len(r) >= 16384:        # keep >= 1 byte for the FE marker
            cur += b'\xFE'
            banks.append(cur.ljust(16384, b'\xff')); cur = bytearray()
        placed.append((len(banks), len(cur)))
        cur += r
    cur += b'\xFD'
    banks.append(cur.ljust(16384, b'\xff'))
    assert len(banks) <= 256
    (ROOT / 'src/config.inc').write_text(f'FIRSTBANK = {FIRSTBANK}\nYOFF = {Y_OFF}\n')
    subprocess.run([str(TOOL / 'sdasz80'), '-los', str(OUT / 'player.rel'), str(ROOT / 'src/player.asm')],
                   cwd=ROOT / 'src', check=True)
    subprocess.run([str(TOOL / 'sdldz80'), '-n', '-i', str(OUT / 'player'), str(OUT / 'player.rel')], cwd=ROOT, check=True)
    code_end = 0
    for line in (OUT / 'player.ihx').read_text().splitlines():
        r = bytes.fromhex(line[1:]); assert sum(r) % 256 == 0
        if r[3] == 0:
            n = r[0]; a = int.from_bytes(r[1:3], 'big')
            if a >= 0xE800:
                code_end = max(code_end, a + n); assert a + n <= 0xF000
                a = a - 0xE800 + 0x4100
            assert 0x4000 <= a and a + n <= 0x8000
            banks[0][a - 0x4000:a - 0x4000 + n] = r[4:4 + n]
    rom = bytearray(b''.join(banks).ljust(ROM_SIZE, b'\xff'))
    assert rom[0x10:0x18] == b'ASCII16X'
    (OUT / 'NICCC.ROM').write_bytes(rom)
    rep = dict(rom_bytes=len(rom), banks_used=len(banks), frames=len(frames),
               stream_bytes=sum(len(record(f)) for f in frames), player_code_bytes=code_end - 0xE800,
               max_verts=max(len(f['verts']) for f in frames), max_faces=max(len(f['faces']) for f in frames),
               sha256=hashlib.sha256(rom).hexdigest())
    (OUT / 'manifest.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))
    return frames


if __name__ == '__main__':
    build(sys.argv[1])
