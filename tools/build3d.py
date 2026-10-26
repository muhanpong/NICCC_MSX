"""Build NICCC3D.ROM: PICONICCC's 3D models and camera paths rendered live by Geo3D.

The ROM is an op stream that a small player (src/player3d.asm) interprets; every
decision is made here, offline:

  01 idx n  data[n]        index idx to port 9Dh, n bytes to 9Fh (Geo3D)
  05 idx lo hi data[len]   the same for long blocks (model uploads)
  02                       Geo3D RUN (CTRL = 03h: run, filled faces), wait until idle
  03 r36..r46              HMMV (11 bytes to R#36..R#46 via 9Bh), after CE = 0
  04                       end of frame: CE = 0, next vertical blank, show the drawn page
  06 idx n  data[n]        palette: R#16 = idx, n bytes to 9Ah (EPAL: R, G, B 5-bit)
  07 reg val               VDP register write
  FE                       continue at the start of the next 16 KiB bank
  FD                       end: start again from the first bank

Per frame, per model (renderList order, one RUN each, so a later model lies over an
earlier one as in the editor): the camera matrix (Q2.14) and translation, then the
near-plane patches: faces that Geo3D would skip (a vertex behind ZNEAR) clipped at
Zc = ZC here and sent as extra faces whose new vertices are interpolated in model
space. Models are uploaded to Geo3D RAM when they appear (first-fit allocation).
Uncovered screen area is cleared with one HMMV of its bounding box.
"""
import os, sys, json, math, hashlib, shutil, subprocess
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene3d import load, Camera, st_level
import geo3d as G

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out'
S = 256
ZNEAR = 8
ZC = 64
F, CX, CY = 100, 128, 106
W, H = 256, 212
ROTOR_DEG = 3.0
ROM_SIZE = 1 << 20
TOOL = Path(os.environ['SDCC_BIN']) if 'SDCC_BIN' in os.environ else None


def q14(x):
    return max(-32768, min(32767, int(round(x * 16384))))


def w16(x):
    return [x & 0xFF, (x >> 8) & 0xFF]


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def area(p, a, b, c):
    (x0, y0), (x1, y1), (x2, y2) = p[a][:2], p[b][:2], p[c][:2]
    return (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)


class Builder:
    def __init__(self):
        self.models, self.cams, self.rl = load()
        cols = sorted({f[0].upper() for m in self.models.values() for f in m['f']} - {'#000000'})
        self.colidx = {c: i + 1 for i, c in enumerate(cols)}
        self.colidx['#000000'] = 0
        self.palette = [(0, 0, 0)] + [tuple(round(st_level(int(c[i:i + 2], 16)) * 31 / 7) for i in (1, 3, 5)) for c in cols]
        assert len(self.palette) <= 256
        self.mv = {n: [tuple(int(round(S * x)) for x in v) for v in m['v']] for n, m in self.models.items()}

    def pose(self, basis, name, f):
        r, u, w, eye = basis
        R = [r, u, w]
        if name == 'rotorin':
            R = matmul(R, rot_y(math.radians(ROTOR_DEG * (f - self.models[name]['fstart']))))
        M = [q14(R[i][j]) for i in range(3) for j in range(3)]
        T = [int(round(-S * sum(a * b for a, b in zip(row, eye)))) for row in (r, u, w)]
        assert all(abs(t) <= 32767 for t in T), (name, f, T)
        return M, T

    def frames(self):
        """[(f, [(name, M, T, patches)])]; patches = [(new model-space vertices, faces)]"""
        cam = Camera(self.cams)
        g = G.Geo3D()
        g.cfg[12:18] = [F, CX & 0xFFFF, CY & 0xFFFF, ZNEAR, W, H]
        out = []
        for f in range(1800):
            runs = []
            for e in self.rl:
                name = e['model']; m = self.models[name]
                if not (m['fstart'] <= f < m['fend']):
                    continue
                cam.update(e['campath'], f)
                M, T = self.pose(cam.basis() + (list(cam.eye),), name, f)
                g.cfg[0:9] = [x & 0xFFFF for x in M]; g.cfg[9:12] = [x & 0xFFFF for x in T]
                verts = self.mv[name]
                proj = [g.transform(v) for v in verts]
                cam_int = [self.cam_coords(M, T, v) for v in verts]
                pverts, pfaces = [], []
                for fc in m['f']:
                    idx = [i - 1 for i in fc[1:]]
                    if all(proj[i] is not None for i in idx):
                        continue
                    if all(cam_int[i][2] < ZC for i in idx):
                        continue
                    poly = self.clip(idx, verts, cam_int)
                    if len(poly) < 3:
                        continue
                    # poly: list of ('v', i) or ('n', model-space vertex)
                    pts = [verts[x] if k == 'v' else x for k, x in poly]
                    if any(g.transform(p) is None for p in pts):
                        continue
                    ref = []
                    for k, x in poly:
                        if k == 'v':
                            ref.append(('v', x))
                        else:
                            pverts.append(x); ref.append(('p', len(pverts) - 1))
                    for q in self.fan(ref):
                        pfaces.append((q, self.colidx[fc[0].upper()]))
                runs.append((name, M, T, pverts, pfaces))
            out.append((f, runs))
        return out

    @staticmethod
    def cam_coords(M, T, v):
        return tuple(((M[3 * k] * v[0] + M[3 * k + 1] * v[1] + M[3 * k + 2] * v[2]) >> 14) + T[k] for k in range(3))

    @staticmethod
    def clip(idx, verts, cz):
        out = []
        n = len(idx)
        for k in range(n):
            a, b = idx[k], idx[(k + 1) % n]
            za, zb = cz[a][2], cz[b][2]
            if za >= ZC:
                out.append(('v', a))
            if (za >= ZC) != (zb >= ZC):
                t = (ZC + 1 - za) / (zb - za)
                out.append(('n', tuple(int(round(verts[a][j] + t * (verts[b][j] - verts[a][j]))) for j in range(3))))
        return out

    @staticmethod
    def fan(ref):
        n = len(ref)
        quads = []
        i = 1
        while i + 1 < n:
            if i + 2 < n:
                quads.append([ref[0], ref[i], ref[i + 1], ref[i + 2]]); i += 2
            else:
                quads.append([ref[0], ref[i], ref[i + 1], ref[i + 1]]); i += 1
        return quads

    # ------------------------------------------------------------------ stream
    def build(self):
        frames = self.frames()
        # model RAM regions: static + the most patch vertices/faces the model ever needs
        need = {}
        for f, runs in frames:
            for name, M, T, pv, pf in runs:
                nv, nf = need.get(name, (0, 0))
                need[name] = (max(nv, len(pv)), max(nf, len(pf)))
        size = {n: (len(self.models[n]['v']) + need[n][0], len(self.models[n]['f']) + need[n][1]) for n in need}
        ops = []
        resident = {}            # name -> (vbase, fbase)
        page = 1
        g = G.Geo3D(); cov = G.VDP()
        g.cfg[12:18] = [F, CX & 0xFFFF, CY & 0xFFFF, ZNEAR, W, H]
        init = self.init_ops()
        for f, runs in frames:
            fops = []
            active = [r[0] for r in runs]
            for n in list(resident):
                if n not in active:
                    del resident[n]
            for name in active:
                if name not in resident:
                    vb = self.alloc([resident[x][0:2] + (size[x][0],) for x in resident], size[name][0], 0)
                    fb = self.alloc([(resident[x][1], resident[x][1], size[x][1]) for x in resident], size[name][1], 1)
                    resident[name] = (vb, fb)
                    fops += self.upload(name, vb, fb)
            run_ops = []
            cov.vram[:] = 0
            for name, M, T, pv, pf in runs:
                vb, fb = resident[name]
                nv0, nf0 = len(self.models[name]['v']), len(self.models[name]['f'])
                o = []
                o += [self.op01(0x00, sum((w16(x & 0xFFFF) for x in M + T), []))]
                if pv:
                    o += [self.op01(0x40, [(vb + nv0) & 0xFF]), self.op01(0x68, [(vb + nv0) >> 8])]
                    o += self.op05(0x50, sum((sum((w16(c & 0xFFFF) for c in v), []) for v in pv), []))
                if pf:
                    o += [self.op01(0x58, [(fb + nf0) & 0xFF]), self.op01(0x6C, [(fb + nf0) >> 8])]
                    recs = []
                    for q, col in pf:
                        ids = [(vb + x) if k == 'v' else (vb + nv0 + x) for k, x in q]
                        recs += self.face_rec(ids, col)
                    o += self.op05(0x52, recs)
                o += [self.op01(0x54, w16(vb)), self.op01(0x56, w16(fb)),
                      self.op01(0x42, [(nv0 + len(pv)) & 0xFF]), self.op01(0x6A, [(nv0 + len(pv)) >> 8]),
                      self.op01(0x59, [(nf0 + len(pf)) & 0xFF]), self.op01(0x6D, [(nf0 + len(pf)) >> 8]),
                      self.op01(0x46, w16(256 * page)), bytes([0x02])]
                run_ops += o
            # coverage of this frame: replay its RUN ops on a scratch Geo3D/VDP
            for op in fops + run_ops:
                self.apply(g, cov, op, coverage=True)
            u = cov.vram[256 * page:256 * page + H, :] == 0
            clear = []
            if u.any():
                ys = np.where(u.any(1))[0]; xs = np.where(u.any(0))[0]
                x0, x1, y0, y1 = int(xs[0]), int(xs[-1]), int(ys[0]), int(ys[-1])
                clear = [bytes([0x03] + w16(x0) + w16(256 * page + y0) + w16(x1 - x0 + 1) + w16(y1 - y0 + 1) + [0, 0, 0xC0])]
            ops.append((f, fops + clear + run_ops + [bytes([0x04])]))
            page ^= 1
        return init, ops, size

    def alloc(self, used, n, _):
        taken = sorted((b, b + s) for b, _b, s in used)
        start = 0
        for a, b in taken:
            if start + n <= a:
                break
            start = max(start, b)
        assert start + n <= 1024, ('Geo3D RAM full', used, n)
        return start

    def face_rec(self, ids, col):
        ids = list(ids) + [ids[-1]] * (4 - len(ids))
        hi = sum((i >> 8 & 3) << (2 * k) for k, i in enumerate(ids))
        return [i & 0xFF for i in ids] + [hi] + [0] * 6 + [col]

    def upload(self, name, vb, fb):
        m = self.models[name]
        o = [self.op01(0x40, [vb & 0xFF]), self.op01(0x68, [vb >> 8])]
        o += self.op05(0x50, sum((sum((w16(c & 0xFFFF) for c in v), []) for v in self.mv[name]), []))
        o += [self.op01(0x58, [fb & 0xFF]), self.op01(0x6C, [fb >> 8])]
        recs = []
        for fc in m['f']:
            recs += self.face_rec([vb + i - 1 for i in fc[1:]], self.colidx[fc[0].upper()])
        o += self.op05(0x52, recs)
        return o

    @staticmethod
    def op01(idx, data):
        assert len(data) < 256
        return bytes([0x01, idx, len(data)] + list(data))

    @staticmethod
    def op05(idx, data):
        out = []
        for i in range(0, len(data), 3072):
            chunk = data[i:i + 3072]
            out.append(bytes([0x05, idx] + w16(len(chunk)) + list(chunk)))
        return out

    def init_ops(self):
        regs = [(0, 0x0E), (1, 0x00), (2, 0x1F), (7, 0), (8, 0x0A), (9, 0x80), (21, 0x00), (20, 0x11), (45, 0)]
        o = [bytes([0x07, r, v]) for r, v in regs]
        pal = sum(([r, g, b] for r, g, b in self.palette), [])
        for i in range(0, len(pal), 255):
            o.append(bytes([0x06, i // 3, len(pal[i:i + 255])] + pal[i:i + 255]))
        o += [self.op01(0x18, sum((w16(x & 0xFFFF) for x in (F, CX, CY, ZNEAR, W, H)), [])),
              self.op01(0x6F, [1]), self.op01(0x44, [0, 0]), self.op01(0x5A, [0] * 6)]
        # clear both pages once
        for p in (0, 1):
            o.append(bytes([0x03] + w16(0) + w16(256 * p) + w16(256) + w16(256) + [0, 0, 0xC0]))
        o += [bytes([0x07, 1, 0x40])]
        return o

    @staticmethod
    def apply(g, vdp, op, coverage=False):
        if op[0] in (0x01, 0x05):
            idx = op[1]
            data = op[3:] if op[0] == 0x01 else op[4:]
            G.geo_write(g, idx, data)
        elif op[0] == 0x02:
            st = dict(skip=0, cull=0, draw=0)
            g.run(vdp, st)


def pack(init, frames, start_bank=1):
    banks = [bytearray()]
    def put(op):
        if len(banks[-1]) + len(op) > 16383:
            banks[-1] += b'\xFE'
            banks.append(bytearray())
        assert len(op) < 16383
        banks[-1] += op
    for op in init:
        put(op)
    for f, ops in frames:
        for op in ops:
            put(op)
    put(b'\xFD')
    return [bytes(b).ljust(16384, b'\xFF') for b in banks]


def assemble():
    tool = TOOL or Path(shutil.which('sdasz80') or 'sdasz80').parent
    src = ROOT / 'src' / 'player3d.asm'
    subprocess.run([str(tool / 'sdasz80'), '-los', str(OUT / 'player3d.rel'), str(src)], cwd=ROOT / 'src', check=True)
    subprocess.run([str(tool / 'sdldz80'), '-n', '-i', str(OUT / 'player3d'), str(OUT / 'player3d.rel')], cwd=ROOT, check=True)
    bank0 = bytearray(b'\xFF' * 16384)
    for line in (OUT / 'player3d.ihx').read_text().splitlines():
        r = bytes.fromhex(line[1:]); assert sum(r) % 256 == 0
        if r[3] != 0:
            continue
        n, a = r[0], int.from_bytes(r[1:3], 'big')
        if a >= 0xE800:
            assert a + n <= 0xF000
            a = a - 0xE800 + 0x4100
        assert 0x4000 <= a and a + n <= 0x8000
        bank0[a - 0x4000:a - 0x4000 + n] = r[4:4 + n]
    return bytes(bank0)


def main():
    b = Builder()
    init, frames, size = b.build()
    banks = pack(init, frames)
    OUT.mkdir(exist_ok=True)
    stream = b''.join(banks)
    rom = bytearray(assemble() + stream)
    assert len(rom) <= ROM_SIZE, len(rom)
    rom = rom.ljust(ROM_SIZE, b'\xFF')
    assert rom[0x10:0x18] == b'ASCII16X'
    (OUT / 'NICCC3D.ROM').write_bytes(rom)
    (OUT / 'stream.bin').write_bytes(stream)
    per = [sum(len(o) for o in ops) for f, ops in frames]
    rep = dict(rom_bytes=len(rom), sha256=hashlib.sha256(rom).hexdigest(), frames=len(frames), banks=len(banks), stream_bytes=len(stream), colours=len(b.palette),
               frame_bytes_median=int(np.median(per)), frame_bytes_max=max(per), ram=size)
    (OUT / 'manifest3d.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != 'ram'}))


if __name__ == '__main__':
    main()
