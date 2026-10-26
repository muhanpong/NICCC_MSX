"""PICONICCC's 3D reconstruction of ST-NICCC 2000 (Megus, github.com/Megus/piconiccc,
json_models/) evaluated per original stream frame, the way its editor does it
(editor/glrender.js, editor/camera.js):

- a model is drawn on frames fstart <= f < fend, in renderList order, each with its
  own camera path; the depth buffer is cleared before every model, so a later model
  lies over an earlier one;
- a camera path is a Catmull-Rom spline through keyframes (eye, dir, up) placed at
  original frame numbers; the first and last keyframes (frame -1) are spline handles;
- the camera is one global state: when a path has no valid segment at f, the last
  computed camera stays (editor behaviour, kept on purpose);
- projection: GL perspective, fov = model.fov (90) vertical, aspect 1, and the editor's
  overlay puts NDC (x, y) on the original 256 x 200 screen at (128 + 100 x, 100 - 100 y).
"""
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'


def load():
    m = json.load(open(DATA / 'models.json'))
    c = json.load(open(DATA / 'camera.json'))
    r = json.load(open(DATA / 'renderList.json'))
    return m, c, r


def _cr(v0, v1, v2, v3, p):
    t2, t3 = p * p, p * p * p
    return 0.5 * (t3 * (-v0 + 3 * v1 - 3 * v2 + v3) + t2 * (2 * v0 - 5 * v1 + 4 * v2 - v3)
                  + p * (-v0 + v2) + 2 * v1)


def _spline(a, b, c, d, p):
    return [_cr(a[i], b[i], c[i], d[i], p) for i in range(3)]


def _norm(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class Camera:
    def __init__(self, paths):
        self.paths = paths
        self.eye, self.dir, self.up = [0, 0, -2], [0, 0, 1], [0, 1, 0]

    def update(self, name, f):
        path = self.paths[name]
        cid = None
        for i, k in enumerate(path):                       # changeCamPath
            if k['frame'] != -1 and f >= k['frame']:
                cid = i
        if cid is None or cid - 1 < 0 or cid + 2 >= len(path) or path[cid + 1]['frame'] == -1:
            return                                         # spline_cam: keep the state
        f0, f1 = path[cid]['frame'], path[cid + 1]['frame']
        t = 0.0 if f == f0 else (f - f0) / (f1 - f0)
        k = [path[cid - 1], path[cid], path[cid + 1], path[cid + 2]]
        self.eye = _spline(*[x['picoEye'] for x in k], t)
        self.dir = _norm(_spline(*[x['picoDir'] for x in k], t))
        self.up = _norm(_spline(*[x['picoUp'] for x in k], t))

    def basis(self):
        """camera axes: right, up, forward (lookAt(eye, eye + dir, up))"""
        fwd = _norm(self.dir)
        # the editor overlays its GL view mirrored (main.js mirrorImage(..., true)), so the
        # data were authored mirrored: screen right = up x fwd, not GL's fwd x up
        right = _norm(_cross(self.up, fwd))
        up = _cross(fwd, right)
        return right, up, fwd


import os
ROTOR_DEG = float(os.environ.get('ROTOR_DEG', '0'))   # 'rotorin' spin about world Y, degrees per frame


def model_at(m, name, f):
    """the editor spins 'rotorin' about (0,1,0) (main.js); everything else is static"""
    if name != 'rotorin' or not ROTOR_DEG:
        return m
    a = math.radians(ROTOR_DEG * (f - m['fstart']))
    c, s_ = math.cos(a), math.sin(a)
    return dict(m, v=[[c * x + s_ * z, y, -s_ * x + c * z] for x, y, z in m['v']])


def frame_scene(models, cams, rlist, f, cam):
    """[(model name, model, (right, up, fwd, eye))] for frame f, in draw order"""
    out = []
    for e in rlist:
        m = model_at(models[e['model']], e['model'], f)
        if m['fstart'] <= f < m['fend']:
            cam.update(e['campath'], f)
            r, u, w = cam.basis()
            out.append((e['model'], m, (r, u, w, list(cam.eye))))
    return out


def to_camera(v, basis):
    r, u, w, eye = basis
    d = [v[0] - eye[0], v[1] - eye[1], v[2] - eye[2]]
    return (_dot(r, d), _dot(u, d), _dot(w, d))


def st_level(v):
    """the models' colours are ST 3-bit levels written as 16*L + 15 (0Fh..7Fh)"""
    return max(0, min(7, (v - 15) // 16))


def hexcol(s):
    return tuple(round(st_level(int(s[i:i + 2], 16)) * 255 / 7) for i in (1, 3, 5))
