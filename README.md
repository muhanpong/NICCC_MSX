# ST-NICCC 2000 on MSX turbo R + V9968 + Geo3D

Personal-use port of the ST-NICCC 2000 polygon stream (Oxygene) as packaged
in PeterLemon/PSX `Demo/PSXNICCC/scene1.bin` (no licence file in that repo;
redistribution terms of the data are unknown: do not redistribute the ROM).
`scene1.bin` is not included; pass its path to the build.

* `out/NICCC.ROM`: 4 MiB, native **ASCII16X** (signature at file offset 0x10;
  bank writes to 6000h, all banks < 256 so addr[11:8] = 0). openMSX picks
  "ASCII16-X" from the signature; the MiSTer core's mapper_detect.sv gives
  the "ASCII16X" signature priority over the bank-write histogram.
* turbo R R800, SCREEN 5 double buffered, V9968 98h-9Ch (EPAL), Geo3D V1 at
  9Dh/9Fh. Each frame: optional HMMV clear (rows 6..205), one Geo3D RUN with
  the frame's prebuilt vertex/face streams, flip at the next vertical blank,
  palette (48 bytes, EPAL) written in that same blank.
* Mapping: vertex (x, y) -> model (x-128, 100-y, 0), identity matrix, TZ = F
  = 256, CX = 128, CY = 106: Geo3D projects exactly onto pixel (x, y+6).
  Equal depth for every face keeps stream order (Geo3D ties -> lower face
  number); zero normals give flat colours. Polygons > 4 vertices become fans
  of quads with the best pivot; faces start at their largest corner.

Build: `python tools/build.py /path/to/scene1.bin` (SDCC sdasz80/sdldz80).
Checks: `tools/verify_render.py SCENE DUMPDIR TAG` against per-update VRAM
dumps from `tools/capture.tcl` (openMSX Geo3D fork, FS-A1ST_V9968).
