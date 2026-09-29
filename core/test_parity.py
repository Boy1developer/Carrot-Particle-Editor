# -*- coding: utf-8 -*-
"""Parity: C++ Engine.sample() vs StudioApp._sample_tracks over a grid.
Deterministic parts must match: size/speed/opacity (1e-9), color (exact),
shape (exact). RNG streams differ by design — tested separately."""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "editor"))
import particle_studio as ps
import particle_core as core

ORDER = ["circle", "square", "triangle", "star", "diamond", "line",
         "custom", "sphere", "cube", "pyramid", "torus", "billboard"]


class Fake:
    ptype = "2d"
    states = [
        {"id": "s0", "role": "birth", "label": "b", "duration": 0.5,
         "shape": "square", "easing": "ease-in",
         "appearance": {"size": 8, "sizeMax": 12, "color": "#ffaa00", "opacity": 255},
         "movement": {"minSpeed": 100, "maxSpeed": 160}},
        {"id": "s1", "role": "mid", "label": "m", "duration": 0.7,
         "shape": "star", "easing": "ease-out",
         "appearance": {"size": 20, "sizeMax": 4, "color": "#123456", "opacity": 100},
         "movement": {"minSpeed": 30, "maxSpeed": 10}},
        {"id": "s2", "role": "death", "label": "d", "duration": 0.5,
         "shape": "circle", "easing": "ease-in-out",
         "appearance": {"size": 2, "sizeMax": 2, "color": "#ff3300", "opacity": 0},
         "movement": {"minSpeed": 20, "maxSpeed": 60}},
    ]
    _build_tracks = ps.StudioApp._build_tracks
    _sample_tracks = ps.StudioApp._sample_tracks
    _locate = staticmethod(ps.StudioApp.__dict__["_locate"].__func__)
    _lerp_color = staticmethod(ps.StudioApp.__dict__["_lerp_color"].__func__)
    _ease_fn = staticmethod(ps.StudioApp.__dict__["_ease_fn"].__func__)


f = Fake()
tracks = f._build_tracks()
eng = core.Engine()
eng.configure({"flow": 40, "maxParticles": 300, "mode": "Infinite",
               "emissionZone": {"shape": "Circle"},
               "propagationCone": {"direction": 0, "spread": 90}},
              tracks, False)

bad = total = 0
for age, sr, spr in itertools.product(
        [0.0, 0.1, 0.249, 0.25, 0.251, 0.5, 0.6, 1.0, 1.19, 1.2, 5.0],
        [0.0, 0.37, 1.0], [0.0, 0.63, 1.0]):
    total += 1
    py = f._sample_tracks(tracks, age, sr, spr)
    cc = eng.sample(age, sr, spr)
    ok = (abs(py["size"] - cc["size"]) < 1e-9
          and abs(py["speed"] - cc["speed"]) < 1e-9
          and abs(py["opacity"] - cc["opacity"]) < 1e-9
          and int(py["color"].lstrip("#"), 16) == cc["color"]
          and ORDER.index(py["shape"]) == cc["shape"])
    if not ok:
        bad += 1
        if bad <= 5:
            print("MISMATCH", age, sr, spr, py, cc)
print(f"parity: {total - bad}/{total} match")
assert bad == 0, f"{bad} mismatches"
print("PARITY OK")
