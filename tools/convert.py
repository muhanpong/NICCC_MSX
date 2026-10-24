"""scene1.bin -> per-frame Geo3D streams.

Screen mapping: vertex (x, y) of the 256x200 ST screen becomes the model
point (x - 128, 100 - y, 0); with the identity matrix, TZ = F = 256,
CX = 128, CY = 106, Geo3D projects it exactly onto pixel (x, y + 6).
Every face has the same depth, so Geo3D paints in face order (ties go to
the lower face number) = stream order.  Normals are zero: shade level 0,
colour = BASE = the polygon's palette index.

Polygons with more than 4 vertices become a fan of quads (plus one
triangle); the fan pivot is chosen per polygon to match the whole-polygon
row fill best.  Each face starts at its largest-area corner (Geo3D culls
by the I0-I1-I2 triangle) and is wound to the visible side.
"""
import struct
from niccc import parse

Y_OFF = 6


def rowspans(face):
    ys = [p[1] for p in face]
    n = len(face)
    out = {}
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
            out[y] = (min(xs), max(xs))
    return out


def fan(pts):
    n = len(pts)
    out = []
    i = 1
    while i + 1 < n:
        if i + 2 < n:
            out.append([0, i, i + 1, i + 2]); i += 2
        else:
            out.append([0, i, i + 1]); i += 1
    return out


def _pix(face):
    s = set()
    for y, (a, b) in rowspans(face).items():
        s.update((x, y) for x in range(a, b + 1))
    return s


def split(pts):
    """Index lists into pts: one face for <= 4 vertices, else the fan with
    the best pivot."""
    n = len(pts)
    if n <= 4:
        return [list(range(n))]
    whole = _pix(pts)
    best = None
    for r in range(n):
        order = [(r + k) % n for k in range(n)]
        faces = [[order[i] for i in f] for f in fan(order)]
        u = set()
        for f in faces:
            u |= _pix([pts[i] for i in f])
        d = len(u ^ whole)
        if best is None or d < best[0]:
            best = (d, faces)
            if d == 0:
                break
    return best[1]


def screen_area(p0, p1, p2):
    # Geo3D: area = (x1-x0)*(y2-y0) - (y1-y0)*(x2-x0) in screen coords, visible if > 0
    return (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])


def orient(ids, pts):
    """Start at the largest corner, wind so the screen area is positive."""
    k = len(ids)
    if k == 3:
        a = screen_area(*(pts[i] for i in ids))
        if a < 0:
            ids = [ids[2], ids[1], ids[0]]
        return ids + [ids[-1]]
    best = max(range(4), key=lambda r: abs(screen_area(*(pts[ids[(r + j) % 4]] for j in range(3)))))
    ids = [ids[(best + j) % 4] for j in range(4)]
    if screen_area(*(pts[i] for i in ids[:3])) < 0:
        ids = [ids[2], ids[1], ids[0], ids[3]]
    return ids


def to_epal(pal):
    return [round(c * 31 / 15) for rgb in pal for c in rgb]


def frames_geo(path):
    """[(flags, palette_or_None, verts[(x,y)], faces[(ids4, colour)])]"""
    out = []
    for f in parse(path):
        vlist, vidx = [], {}

        def vid(p):
            if p not in vidx:
                vidx[p] = len(vlist); vlist.append(p)
            return vidx[p]
        faces = []
        for col, pts in f['polys']:
            for ids in split(pts):
                sub = [pts[i] for i in ids]
                o = orient(list(range(len(sub))), sub)
                faces.append(([vid(sub[i]) for i in o], col))
        assert len(vlist) <= 255 and len(faces) <= 255, (len(vlist), len(faces))
        flags = (1 if f['clear'] else 0) | (2 if f['pal_changes'] else 0)
        out.append(dict(flags=flags, palette=to_epal(f['palette']) if f['pal_changes'] else None,
                        full_palette=to_epal(f['palette']), verts=vlist, faces=faces))
    return out


def record(fr):
    vb = b''.join(struct.pack('<hhh', x - 128, 100 - y, 0) for x, y in fr['verts'])
    fb = b''.join(bytes(ids) + struct.pack('<hhh', 0, 0, 0) + bytes([col]) for ids, col in fr['faces'])
    body = bytes([len(fr['verts']), len(fr['faces'])]) + struct.pack('<HH', len(vb), len(fb)) + vb + fb
    pal = bytes(fr['palette']) if fr['palette'] else b''
    return bytes([fr['flags']]) + pal + body
