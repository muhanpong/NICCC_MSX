"""out/stream.bin -> stimulus for the MSX1 core's sim/geo3d_perf bench (tb_geo3d_perf.sv).

  stream2stim.py OUT.txt FIRST LAST [dump frames a,b,c] [qdir]
Frames before FIRST only load Geo3D state (no RUN, no clear) so the RAM and pages match;
frames FIRST..LAST run in full. Dump frames end with 'Q page file' (page read back)."""
import sys
from pathlib import Path

def main(out, first, last, dumps=(), qdir='.'):
    blob = (Path(__file__).resolve().parent.parent / 'out/stream.bin').read_bytes()
    L = []
    bank, ptr, frame, page = 0, 0, 0, 1
    while frame <= last:
        base = bank * 16384
        op = blob[base + ptr]; ptr += 1
        live = frame >= first
        if op == 0xFE: bank += 1; ptr = 0; continue
        if op == 0xFD: break
        if op in (0x01, 0x05):
            idx = blob[base + ptr]; ptr += 1
            if op == 0x01: n = blob[base + ptr]; ptr += 1
            else: n = blob[base + ptr] | blob[base + ptr + 1] << 8; ptr += 2
            L.append(f"W 0 {idx:02x}"); L += [f"W 1 {b:02x}" for b in blob[base + ptr:base + ptr + n]]; ptr += n
        elif op == 0x02:
            if live: L += ["W 0 48", "W 1 03", "R"]
        elif op == 0x03:
            r = blob[base + ptr:base + ptr + 11]; ptr += 11
            if live or frame == 0:
                L.append("C"); L += [f"V {36 + k} {r[k]:02x}" for k in range(11)]
        elif op == 0x04:
            if live:
                L.append("C")
                if frame in dumps: L.append(f"Q {page} {qdir}/q{frame:04d}.bin")
                L.append(f"D {256 * page}")
            frame += 1; page ^= 1
        elif op == 0x06:
            n = blob[base + ptr + 1]; ptr += 2 + n
        elif op == 0x07:
            L.append(f"V {blob[base + ptr]} {blob[base + ptr + 1]:02x}"); ptr += 2
    open(out, 'w').write('\n'.join(L) + '\n')
    print(len(L), 'lines,', sum(1 for x in L if x == 'R'), 'RUNs')

if __name__ == '__main__':
    a = sys.argv
    main(a[1], int(a[2]), int(a[3]), [int(x) for x in a[4].split(',')] if len(a) > 4 and a[4] else (), a[5] if len(a) > 5 else '.')
