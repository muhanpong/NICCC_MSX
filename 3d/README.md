# NICCC 3D — ST-NICCC 2000 rebuilt in 3D, drawn live by Geo3D

The scene of Oxygene's STNICCC 2000 Demo as a real 3D world: every frame the MSX
sends one camera matrix per model, and the Geo3D chip transforms, culls, depth-sorts
and fills the polygons on a V9968 in SCREEN 8. No precomputed pictures.

Video and the flat 2D port: see the top of this repository (`../README.md`).

## Credits

- Original demo: **STNICCC 2000 Demo** by Oxygene — GFX (2d and 3d movie) Mon,
  music Laxity / Kefrens, main coding Leonard, STE 50 kHz player Lance
  (<https://www.pouet.net/prod.php?which=1251>).
- **3D models and camera paths: Megus**, from his PICO-8 port PICONICCC
  (<https://github.com/Megus/piconiccc>, `json_models/`, copied unchanged into `data/`).
  He reconstructed the scene by hand and exported the JSON for reuse on request
  (<https://www.pouet.net/topic.php?which=11559&page=6>). The picture is his
  reconstruction, so it is close to, not identical with, Oxygene's original.
- This MSX version: muhanpong. Code under the repository's MIT licence; the data in
  `data/` stays Megus's work and is not covered by it.

## Requirements

- Any MSX with a **V9968** (SCREEN 8 + EPAL) and **Geo3D v2.0** at 9Dh/9Fh. It uses
  v2.0 features (1024-entry model RAM, VFIRST/FFIRST, extended faces), so Geo3D v1.x
  does not run it.
- Tested in openMSX with Geo3D v2 support (a local patch of the Geo3D fork; the public
  fork is v1): all 1800 frames, 59.3 fps. **Not yet confirmed on real hardware**
  (MiSTer MSX1 core V9968 build, which has Geo3D v2, is the target).
- `NICCC3D.ROM`: 1 MiB, ASCII16X.
- Speed: Geo3D fills each face row by row with V9968 LINE commands. A custom option in the
  MiSTer MSX1 core's V9968 build (OSD "Geo3D fill (SCREEN 8)" = HMMV, not part of upstream
  Geo3D) sends those rows as one-row HMMV instead: same pixels, about twice as fast on the
  V9968 (RTL bench: a tunnel frame 17.1 -> 9.2 ms). The ROM runs the same either way.

## How it works

- `tools/scene3d.py`: the scene per original frame. Cameras are Catmull-Rom splines through
  keyframes at original frame numbers, as in PICONICCC's editor (whose view is mirrored);
  colours are ST 3-bit levels; the inner rotor spins 3 degrees a frame (an estimate).
- Geo3D skips any face with a vertex behind the near plane; `tools/build3d.py` clips those
  faces offline per frame and sends them as patch faces (median 14 a frame), so tunnel
  walls near the camera stay whole.
- The ROM is an op stream for a small player (`src/player3d.asm`): Geo3D register
  blocks, RUN, HMMV clears of the uncovered area only, palette, page flip.
- `tools/geo3d.py` is a behavioural model of Geo3D v2 + SCREEN 8; `tools/verify3d.py`
  compares it with a floating-point reference, and openMSX VRAM dumps
  (`tools/capture3d.tcl`) matched it on all 1800 frames.

## Build

    cd 3d && python tools/build3d.py        # out/NICCC3D.ROM (needs SDCC sdasz80/sdldz80)

`tools/render_ref.py` compares with the original 2D stream: set `NICCC_SCENE` to
`scene1.bin` or an original Oxygene disk image.
