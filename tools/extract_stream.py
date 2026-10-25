"""Extract the ST-NICCC 2000 polygon stream (scene1.bin) from an original Oxygene disk.

  python tools/extract_stream.py DISK.MSA|DISK.ST [OUT.BIN]

Both releases carry the same 639,976-byte stream as a contiguous run of sectors:
  party version 2000 (OXYGEN.MSA, files.dhs.nu/party/stniccc2000/oxygen.zip)  at byte 142848
  final version 2013 (ST-NICC2.msa, leonard.oxg.free.fr/demos/atari/ST-NICC2.zip) at byte 162304
The output is checked against the stream's MD5 (the file the 2019 porting challenge
handed out, also in FsNICC and PeterLemon/PSX).
"""
import hashlib
import struct
import sys
from pathlib import Path

STREAM_LEN = 639976
STREAM_MD5 = '0c529b0e6822d39dfba9eaf2d8332cae'
KNOWN_OFFSETS = (142848, 162304)


def msa_to_st(d):
    """Atari MSA disk image -> raw sector image (RLE marker E5h, value, 16-bit count)."""
    mid, spt, sides, first, last = struct.unpack('>HHHHH', d[:10])
    if mid != 0x0E0F:
        raise ValueError('not an MSA image')
    p, out, track_len = 10, bytearray(), spt * 512
    for _ in range(first, last + 1):
        for _ in range(sides + 1):
            n = struct.unpack('>H', d[p:p + 2])[0]
            blk = d[p + 2:p + 2 + n]
            p += 2 + n
            if n == track_len:
                out += blk
                continue
            i = 0
            while i < len(blk):
                if blk[i] == 0xE5:
                    out += bytes([blk[i + 1]]) * struct.unpack('>H', blk[i + 2:i + 4])[0]
                    i += 4
                else:
                    out.append(blk[i])
                    i += 1
    return bytes(out)


def extract(disk):
    d = Path(disk).read_bytes()
    img = msa_to_st(d) if d[:2] == b'\x0e\x0f' else d
    for off in KNOWN_OFFSETS:
        s = img[off:off + STREAM_LEN]
        if hashlib.md5(s).hexdigest() == STREAM_MD5:
            return s
    raise SystemExit(f'{disk}: no ST-NICCC 2000 stream at the known offsets (md5 {STREAM_MD5})')


if __name__ == '__main__':
    s = extract(sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else 'scene1.bin')
    out.write_bytes(s)
    print(f'{out}: {len(s)} bytes, md5 {STREAM_MD5}')
