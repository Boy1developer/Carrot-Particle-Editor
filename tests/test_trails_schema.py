# -*- coding: utf-8 -*-
"""Trail settings schema: defaults <-> TRAIL_SCHEMA sync + clamp rules."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "editor"))
import particle_studio as PS

d = PS.default_trails()
keys = [f["key"] for f in PS.TRAIL_SCHEMA]
assert sorted(d) == sorted(keys), "defaults/schema drift: %s" % (
    set(d) ^ set(keys),)
for f in PS.TRAIL_SCHEMA:
    assert f["type"] in ("bool", "int", "float", "combo", "color", "text",
                         "file", "curve", "gradient-color", "gradient-alpha"), f
    assert f["sec"] in "ABCDEFG", f
    assert f["modes"] in ("2d3d", "3d"), f
    assert f.get("hint"), f["key"]
# clamps
assert PS.sanitize_trails({"lifetime": 999})["lifetime"] == 30.0
assert PS.sanitize_trails({"lifetime": -5})["lifetime"] == 0.05
assert PS.sanitize_trails({"space": "x"})["space"] == "world"
assert PS.sanitize_trails({"maxPoints": "a"})["maxPoints"] == 32
assert PS.sanitize_trails({"timeScale": 9})["timeScale"] == 5.0
assert PS.sanitize_trails({"capStyle": "round"})["capStyle"] == "round"
assert PS.sanitize_trails({"capStyle": "x"})["capStyle"] == "flat"
# LUT sizes + determinism
assert len(PS.bake_curve(d["widthCurve"])) == 64
assert len(PS.bake_gradient(d["colorStops"], d["alphaStops"])) == 256
assert PS.bake_curve(d["widthCurve"]) == PS.bake_curve(d["widthCurve"])
print("TRAILS-SCHEMA-OK")
