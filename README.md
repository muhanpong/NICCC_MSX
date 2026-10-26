# NICCC 3D — ST-NICCC 2000 rebuilt in 3D, drawn live by Geo3D (work in progress)

The 3D scene is Megus's reconstruction from PICONICCC (PICO-8 port, 2020;
<https://github.com/Megus/piconiccc>, `json_models/`, exported by him for reuse on
request: <https://www.pouet.net/topic.php?which=11559&page=6>). Original demo:
STNICCC 2000 by Oxygene (<https://www.pouet.net/prod.php?which=1251>).

MSX turbo R (or any MSX) + V9968 (SCREEN 8 + EPAL) + Geo3D v2. Every frame the
player sends one camera matrix per model and Geo3D does the transform, back-face
culling, depth order and filling; faces crossing the near plane are clipped offline
and sent as patch faces.

- `tools/scene3d.py`   the scene per original frame (camera splines as in the editor)
- `tools/render_ref.py` float reference vs Geo3D rules
- `tools/geo3d.py`     Geo3D v2 + SCREEN 8 behavioural model, runs the ROM stream
- `tools/build3d.py`   `out/NICCC3D.ROM` (1 MiB ASCII16X) from the JSON data
- `tools/verify3d.py`  stream vs reference; `tools/capture3d.tcl` openMSX dumps
- `src/player3d.asm`   the op-stream player
