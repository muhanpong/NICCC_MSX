"""A behavioural model of what the MSX sees: the player's op stream (build3d.py) run
against Geo3D v2 (rtl/video/geo3d/geo3d_engine.v, geo3d_core.v) and a SCREEN 8 V9968.

Not cycle-exact and not a bit-exact rasteriser: the row filling follows the
engine's comment (span between the leftmost and rightmost edge crossing, clipped
to the screen), with floor division. It is the reference for what each frame
should look like, to compare with openMSX VRAM dumps within a tolerance.
"""
import numpy as np

W, H = 256, 212


def sat18(x):
    return max(-(1 << 17), min((1 << 17) - 1, x))


class Geo3D:
    def __init__(self):
        self.cfg = [0] * 18            # M00..M22 TX TY TZ F CX CY ZNEAR W H (words)
        self.vram = [(0, 0, 0)] * 1024
        self.fram = [((0, 0, 0, 0), 0)] * 1024
        self.reg = {}
        self.vaddr = self.faddr = 0
        self.vfirst = self.ffirst = self.nvert = self.nface = 0
        self.ypage = 0

    @staticmethod
    def s16(x):
        return x - 65536 if x & 0x8000 else x

    def transform(self, v):
        c = self.cfg
        m = [self.s16(c[i]) for i in range(9)]
        t = [self.s16(c[9 + i]) for i in range(3)]
        out = []
        for k in range(3):
            acc = m[3 * k] * v[0] + m[3 * k + 1] * v[1] + m[3 * k + 2] * v[2]
            out.append(sat18((acc >> 14) + t[k]))
        xc, yc, zc = out
        f, cx, cy, zn = c[12], self.s16(c[13]), self.s16(c[14]), self.s16(c[15])
        if zc < zn or zc <= 0:
            return None
        px, py = abs(xc) * f // zc, abs(yc) * f // zc
        if px > 32767 or py > 32767:
            return None
        return (cx + (px if xc >= 0 else -px), cy - (py if yc >= 0 else -py), zc)

    def run(self, vdp, stats):
        proj = {}
        for k in range(self.nvert):
            i = (self.vfirst + k) & 1023
            proj[i] = self.transform(self.vram[i])
        faces = []
        for k in range(self.nface):
            fi = (self.ffirst + k) & 1023
            idx, col = self.fram[fi]
            p = [proj.get(i) for i in idx]
            if any(q is None for q in p):
                stats['skip'] += 1
                continue
            (x0, y0, _), (x1, y1, _), (x2, y2, _) = p[:3]
            if (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0) <= 0:
                stats['cull'] += 1
                continue
            faces.append((-sum(q[2] for q in p), k, col, p))
        for _, _, col, p in sorted(faces):
            stats['draw'] += 1
            vdp.fill_poly(p, col, self.ypage)


class VDP:
    """SCREEN 8: two 256 x 256 byte pages, page n at y = 256 n"""
    def __init__(self):
        self.vram = np.zeros((512, 256), np.uint8)
        self.shown = 0
        self.spans = 0
        self.pixels = 0

    def fill_poly(self, p, col, ypage):
        n = len(p)
        ys = [q[1] for q in p]
        for y in range(max(0, min(ys)), min(H - 1, max(ys)) + 1):
            xs = []
            for k in range(n):
                (xa, ya), (xb, yb) = p[k][:2], p[(k + 1) % n][:2]
                if ya == yb:
                    if y == ya:
                        xs += [xa, xb]
                elif min(ya, yb) <= y <= max(ya, yb):
                    xs.append(xa + ((y - ya) * (xb - xa)) // (yb - ya))
            if not xs:
                continue
            a, b = max(0, min(xs)), min(W - 1, max(xs))
            if a <= b:
                self.vram[ypage + y, a:b + 1] = col
                self.spans += 1
                self.pixels += b - a + 1

    def hmmv(self, x, y, nx, ny, col):
        self.vram[y:y + ny, x:x + nx] = col


def run_stream(blob, start_bank, on_frame):
    """execute the ROM op stream; on_frame(index, vdp, geo, stats) after each flip"""
    geo, vdp = Geo3D(), VDP()
    bank, ptr = start_bank, 0
    frame = 0
    stats = dict(skip=0, cull=0, draw=0)
    page = 1                                   # the player draws into the hidden page
    while True:
        base = bank * 16384
        op = blob[base + ptr]; ptr += 1
        if op == 0xFE:
            bank += 1; ptr = 0; continue
        if op == 0xFD:
            return
        if op in (0x01, 0x05):
            idx = blob[base + ptr]; ptr += 1
            if op == 0x01:
                n = blob[base + ptr]; ptr += 1
            else:
                n = blob[base + ptr] | blob[base + ptr + 1] << 8; ptr += 2
            data = blob[base + ptr:base + ptr + n]; ptr += n
            geo_write(geo, idx, data)
        elif op == 0x06:
            n = blob[base + ptr + 1]; ptr += 2 + n
        elif op == 0x07:
            ptr += 2
        elif op == 0x02:
            geo.run(vdp, stats)
        elif op == 0x03:
            r = blob[base + ptr:base + ptr + 11]; ptr += 11
            vdp.hmmv(r[0] | r[1] << 8, r[2] | r[3] << 8, r[4] | r[5] << 8, r[6] | r[7] << 8, r[8])
        elif op == 0x04:
            vdp.shown = page
            on_frame(frame, vdp, geo, stats)
            frame += 1
            stats = dict(skip=0, cull=0, draw=0)
            page ^= 1
        else:
            raise ValueError(f'bad op {op:02x} at bank {bank} +{ptr - 1:04x}')


def geo_write(g, idx, data):
    """index idx then the bytes to the data port, with the engine's auto-increment"""
    if idx < 0x24:                             # core configuration, little-endian words
        b = bytearray()
        for i in range(0, 36):
            b += bytes([g.cfg[i // 2] & 0xFF if i % 2 == 0 else g.cfg[i // 2] >> 8])
        for k, v in enumerate(data):
            b[(idx + k) % 36] = v
        g.cfg = [b[2 * i] | b[2 * i + 1] << 8 for i in range(18)]
        return
    if idx == 0x50:                            # VDATA: 6 bytes per vertex
        for i in range(0, len(data), 6):
            w = [data[i + 2 * k] | data[i + 2 * k + 1] << 8 for k in range(3)]
            g.vram[g.vaddr] = tuple(Geo3D.s16(x) for x in w)
            g.vaddr = (g.vaddr + 1) & 1023
        return
    if idx == 0x52:                            # FDATA, extended mode: 12 bytes per face
        for i in range(0, len(data), 12):
            f = data[i:i + 12]
            hi = f[4]
            idxs = tuple(f[k] | ((hi >> (2 * k)) & 3) << 8 for k in range(4))
            g.fram[g.faddr] = (idxs, f[11])
            g.faddr = (g.faddr + 1) & 1023
        return
    # plain registers (the builder never crosses an auto-increment block)
    for k, v in enumerate(data):
        r = idx + k
        lo = lambda x: (x & 0x300) | v
        hi = lambda x: (x & 0xFF) | (v & 3) << 8
        if r == 0x40: g.vaddr = lo(g.vaddr)
        elif r == 0x68: g.vaddr = hi(g.vaddr)
        elif r == 0x58: g.faddr = lo(g.faddr)
        elif r == 0x6C: g.faddr = hi(g.faddr)
        elif r == 0x42: g.nvert = lo(g.nvert)
        elif r == 0x6A: g.nvert = hi(g.nvert)
        elif r == 0x59: g.nface = lo(g.nface)
        elif r == 0x6D: g.nface = hi(g.nface)
        elif r == 0x54: g.vfirst = lo(g.vfirst)
        elif r == 0x55: g.vfirst = hi(g.vfirst)
        elif r == 0x56: g.ffirst = lo(g.ffirst)
        elif r == 0x57: g.ffirst = hi(g.ffirst)
        elif r == 0x46: g.ypage = (g.ypage & 0x700) | v
        elif r == 0x47: g.ypage = (g.ypage & 0xFF) | (v & 7) << 8
        g.reg[r] = v
