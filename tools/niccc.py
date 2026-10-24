"""ST-NICCC 2000 polygon stream (scene1.bin) parser.

Frame:  flags (bit0 clear screen, bit1 palette, bit2 indexed)
        [palette: 16-bit mask (bit15 = colour 0), then one ST/STE word per set bit]
        [indexed: vertex count, count x (x, y)]
        polygons: descriptor (hi nibble colour, lo nibble vertex count), then
                  vertex indices (indexed) or (x, y) pairs
        0xFF end of frame, 0xFE end of frame + skip to next 64 KiB block,
        0xFD end of stream.   Screen 256 x 200.
"""
from pathlib import Path


def ste_level(n):
    """STE 4-bit channel: bit 3 is the LSB, bits 2..0 the high bits."""
    return ((n & 7) << 1) | ((n >> 3) & 1)


def parse(path):
    d = Path(path).read_bytes()
    p = 0
    frames = []
    pal = [(0, 0, 0)] * 16
    while True:
        start = p
        flags = d[p]; p += 1
        fr = dict(clear=bool(flags & 1), indexed=bool(flags & 4), pal_changes=0, polys=[], offset=start)
        if flags & 2:
            mask = (d[p] << 8) | d[p + 1]; p += 2
            pal = list(pal)
            for i in range(16):
                if mask & (0x8000 >> i):
                    w = (d[p] << 8) | d[p + 1]; p += 2
                    pal[i] = (ste_level((w >> 8) & 15), ste_level((w >> 4) & 15), ste_level(w & 15))
                    fr['pal_changes'] += 1
        fr['palette'] = pal
        verts = None
        if flags & 4:
            n = d[p]; p += 1
            verts = [(d[p + 2 * i], d[p + 2 * i + 1]) for i in range(n)]
            p += 2 * n
            fr['nverts_indexed'] = n
        while True:
            desc = d[p]; p += 1
            if desc in (0xFF, 0xFE, 0xFD):
                end = desc
                break
            col, nv = desc >> 4, desc & 15
            if verts is not None:
                pts = [verts[d[p + i]] for i in range(nv)]; p += nv
            else:
                pts = [(d[p + 2 * i], d[p + 2 * i + 1]) for i in range(nv)]; p += 2 * nv
            fr['polys'].append((col, pts))
        fr['size'] = p - start
        frames.append(fr)
        if end == 0xFE:
            p = (p + 0xFFFF) & ~0xFFFF
        if end == 0xFD:
            break
    return frames


if __name__ == '__main__':
    import sys
    fr = parse(sys.argv[1])
    print(len(fr), 'frames;', sum(f['clear'] for f in fr), 'clear;', sum(f['indexed'] for f in fr), 'indexed;',
          sum(f['pal_changes'] > 0 for f in fr), 'palette frames')
