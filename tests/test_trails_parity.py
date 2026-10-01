# -*- coding: utf-8 -*-
"""Trail settings parity: Python bake vs C++ parsed tables must match."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "editor"))
import particle_core as PC
import particle_studio as PS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS = [
    {"dur": 0.5, "shape": "circle", "size": 8, "sizeMax": 12,
     "color": "#ffaa00", "opacity": 255, "minSpeed": 60, "maxSpeed": 160,
     "easing": "linear"},
    {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 4,
     "color": "#ff3300", "opacity": 0, "minSpeed": 20, "maxSpeed": 60,
     "easing": "ease-out"},
]

cases = ["trail_comet_2d", "trail_sword_slash_2d", "trail_smoke_ribbon_3d",
         "trail_energy_beam_3d"]
for name in cases:
    with open(os.path.join(ROOT, "presets", name + ".json"),
              encoding="utf-8") as f:
        eff = json.load(f)
    em = eff["emitter"]
    e = PC.Engine()
    e.configure(em, TRACKS, eff["type"] == "3d")
    t = e.trails_luts()
    py_w = PS.bake_curve(em["trails"]["widthCurve"])
    assert all(abs(a - b) < 1e-9 for a, b in zip(t["w"], py_w)), name
    py_c = PS.bake_gradient(em["trails"]["colorStops"],
                            em["trails"]["alphaStops"])
    for i, p in enumerate(py_c):
        assert tuple(p) == (t["r"][i], t["g"][i], t["b"][i], t["a"][i]), name
    assert bool(t["enabled"]) == bool(em["trails"]["enabled"]), name
    assert t["maxPoints"] == em["trails"]["maxPoints"], name
    assert abs(t["lifetime"] - em["trails"]["lifetime"]) < 1e-9, name
    assert abs(t["minDist"] - em["trails"]["minDist"]) < 1e-9, name
print("TRAILS-PARITY-OK")
