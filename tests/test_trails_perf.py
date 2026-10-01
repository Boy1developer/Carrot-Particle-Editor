# -*- coding: utf-8 -*-
"""Trail perf: 300 trails x 32 points history update + LUT bake cost."""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "editor"))
import particle_studio as PS

from studio_imgui import SimEngine  # noqa: E402  (needs editor/ on path)

random.seed(7)
em = PS.default_emitter("2d")
em["trails"].update({"enabled": True, "maxPoints": 32, "minDist": 2.0,
                     "minTime": 0.0})
sim = SimEngine()
pts = [(i, random.uniform(0, 800), random.uniform(0, 600), 0.0)
       for i in range(300)]
t0 = time.time()
for _ in range(120):
    moved = [(k, x + random.uniform(-6, 6), y + random.uniform(-6, 6), z)
             for (k, x, y, z) in pts]
    pts = moved
    sim.update_trails(em, moved, 400.0, 300.0, 0.0, 1.0 / 60.0)
ms = (time.time() - t0) / 120.0 * 1000.0
t0 = time.time()
for _ in range(60):
    PS.bake_curve(em["trails"]["widthCurve"])
    PS.bake_gradient(em["trails"]["colorStops"], em["trails"]["alphaStops"])
bake = (time.time() - t0) / 60.0 * 1000.0
print("trails: %d verts: %d update: %.3fms/frame bake: %.3fms/change" % (
    len(sim.trail_hist),
    sum(len(h) for h in sim.trail_hist.values()), ms, bake))
assert ms < 4.0, "trail history too slow: %.3fms" % ms
print("TRAILS-PERF-OK")
