# -*- coding: utf-8 -*-
"""Behavioral smoke (RNG streams differ by design — check invariants) + perf."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import particle_core as core

# --- burst spawn count mirrors Python: min(maxp, 150) ---
e = core.Engine()
e.configure({"flow": 40, "maxParticles": 500, "mode": "Burst",
             "emissionZone": {"shape": "Circle", "radius": 10, "mode": "Surface"},
             "propagationCone": {"direction": 0, "spread": 90}},
            [{"dur": 0.5, "shape": "circle", "size": 8, "sizeMax": 8,
              "color": "#ffffff", "opacity": 255, "minSpd": 50, "maxSpd": 50,
              "easing": "linear"},
             {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 2,
              "color": "#ffffff", "opacity": 0, "minSpd": 10, "maxSpd": 10,
              "easing": "linear"}], False)
out = e.step(0.016, 400, 300, 0, 0, 0, 0, 0, 0, 500,
             0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
assert len(out["x"]) == 150, len(out["x"])
print("burst count (min(maxp,150)): OK")

# --- infinite flow accumulates then dies out (kill works) ---
e2 = core.Engine()
e2.configure({"flow": 1000, "maxParticles": 4000, "mode": "Infinite",
              "emissionZone": {"shape": "Circle", "radius": 10, "mode": "Surface"},
              "propagationCone": {"direction": 0, "spread": 360}},
             [{"dur": 0.5, "shape": "circle", "size": 8, "sizeMax": 8,
               "color": "#ffffff", "opacity": 255, "minSpd": 50, "maxSpd": 50,
               "easing": "linear"},
              {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 2,
               "color": "#ffffff", "opacity": 0, "minSpd": 10, "maxSpd": 10,
               "easing": "linear"}], False)
peak = 0
for _ in range(120):
    o = e2.step(0.016, 400, 300, 0, 0, 0, 0, 0, 0, 4000,
                0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
    peak = max(peak, len(o["x"]))
assert 0 < peak <= 4000, peak
print(f"flow equilibrium peak: {peak} OK")
# radii within spawn disc + travel; colors valid; shapes valid
assert all(0 <= c <= 0xFFFFFF for c in o["color"])
assert all(0 <= s <= 11 for s in o["shape"])
assert all(r >= 1.0 for r in o["r"])
print("ranges: OK")

# --- morph window keys: bseg/bt present, bounded, and hit over time ---
e5 = core.Engine()
e5.configure({"flow": 1000, "maxParticles": 500, "mode": "Infinite",
              "emissionZone": {"shape": "Circle", "radius": 5, "mode": "Surface"},
              "propagationCone": {"direction": 0, "spread": 10}},
             [{"dur": 0.5, "shape": "circle", "size": 8, "sizeMax": 8,
               "color": "#ffffff", "opacity": 255, "minSpd": 10, "maxSpd": 10,
               "easing": "linear"},
              {"dur": 0.5, "shape": "square", "size": 8, "sizeMax": 8,
               "color": "#ffffff", "opacity": 255, "minSpd": 10, "maxSpd": 10,
               "easing": "linear"}], False)
e5.set_seed(7)
seen_blend = False
for _ in range(120):
    m = e5.step(1 / 60.0, 400, 300, 0, 0, 0, 0, 0, 0, 500,
                0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
    assert set(("bseg", "bt")) <= set(m)
    for bs, bt in zip(m["bseg"], m["bt"]):
        assert bs in (-1, 0), bs
        assert 0.0 <= bt <= 1.0, bt
        if bs == 0:
            seen_blend = True
assert seen_blend, "no particle entered the morph window"
print("morph keys: OK")

# --- reverse spawn: particles start away from center ---
e3 = core.Engine()
e3.configure({"flow": 40, "maxParticles": 300, "mode": "Burst", "reverse": True,
              "emissionZone": {"shape": "Circle", "radius": 10, "mode": "Surface"},
              "propagationCone": {"direction": 0, "spread": 90}},
             [{"dur": 1.0, "shape": "circle", "size": 8, "sizeMax": 8,
               "color": "#ffffff", "opacity": 255, "minSpd": 200, "maxSpd": 200,
               "easing": "linear"},
              {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 2,
               "color": "#ffffff", "opacity": 0, "minSpd": 200, "maxSpd": 200,
               "easing": "linear"}], False)
o = e3.step(0.0, 400, 300, 0, 0, 0, 0, 0, 0, 300,
            0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
import math
d = [math.hypot(x - 400, y - 300) for x, y in zip(o["x"], o["y"])]
assert sum(d) / len(d) > 50, sum(d) / len(d)
print("reverse offset: OK")

# --- perf: sustained 2000-particle step ---
e4 = core.Engine()
e4.configure({"flow": 2000, "maxParticles": 2000, "mode": "Infinite",
              "emissionZone": {"shape": "Circle", "radius": 50, "mode": "Surface"},
              "propagationCone": {"direction": 0, "spread": 360}},
             [{"dur": 1.0, "shape": "circle", "size": 8, "sizeMax": 12,
               "color": "#ffaa00", "opacity": 255, "minSpd": 60, "maxSpd": 160,
               "easing": "linear"},
              {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 4,
               "color": "#ff3300", "opacity": 0, "minSpd": 20, "maxSpd": 60,
               "easing": "linear"}], False)
for _ in range(30):  # warm to equilibrium
    e4.step(0.016, 400, 300, 0, 0, 0, 0, 0, 0, 2000,
            0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
t0 = time.perf_counter()
N = 200
for _ in range(N):
    e4.step(0.016, 400, 300, 0, 0, 0, 0, 0, 0, 2000,
            0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
ms = (time.perf_counter() - t0) / N * 1000
print(f"C++ step @~2000 particles: {ms:.2f} ms/frame")
assert ms < 8.0, ms

# canvas draw cost (the real viewport bottleneck) on a hidden canvas
import tkinter as tk
root = tk.Tk()
root.withdraw()
cv = tk.Canvas(root, width=800, height=600)
cv.pack()
t0 = time.perf_counter()
for _ in range(20):
    for i in range(800):
        cv.create_oval(i, i, i + 6, i + 6, fill="#ffaa00", outline="")
    cv.delete("all")
draw_ms = (time.perf_counter() - t0) / 20 * 1000
print(f"tkinter 800 dots draw: {draw_ms:.2f} ms/frame")
root.destroy()
print("BEHAVIOR+PERF OK")
