# -*- coding: utf-8 -*-
"""Trail emission flow: Godot-style distance mode vs legacy time mode."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "editor"))
import particle_studio as PS

from studio_imgui import SimEngine  # noqa: E402  (needs editor/ on path)

DT = 1.0 / 60.0

# --- defaults keep old files identical ---
d = PS.default_trails()
assert d["emitMode"] == "time" and d["sectionLength"] == 8.0
assert PS.sanitize_trails({"sectionLength": -5})["sectionLength"] == 0.0
assert PS.sanitize_trails({"sectionLength": 9999})["sectionLength"] == 512.0
assert PS.sanitize_trails({"emitMode": "bogus"})["emitMode"] == "time"
assert [f["key"] for f in PS.TRAIL_SCHEMA].count("emitMode") == 1
assert [f["key"] for f in PS.TRAIL_SCHEMA].count("sectionLength") == 1
print("TRAILS-FLOW-DEFAULTS-OK")


def dist_em(**kw):
    em = PS.default_emitter("2d")
    em["trails"].update({"enabled": True, "source": "particles",
                         "emitMode": "distance", "maxPoints": 10,
                         "sectionLength": 5.0, "minTime": 0.0,
                         "lifetimeJitter": 0.0})
    em["trails"].update(kw)
    return em


def run(em, frames, step, start=0.0):
    sim = SimEngine()
    x = start
    for _ in range(frames):
        x += step
        sim.update_trails(em, [(1, x, 0.0, 0.0)], 0.0, 0.0, 0.0, DT)
    return sim


def gaps(hist):
    xs = [p[0] for p in hist]
    return [b - a for a, b in zip(xs, xs[1:])]


# --- distance mode: fixed count, fixed spacing (Godot sections) ---
sim = run(dist_em(), 200, 1.0)  # 1 unit/frame, section every 5 frames
h = sim.trail_hist[1]
assert len(h) == 10, len(h)
for g in gaps(h):
    assert abs(g - 5.0) < 1e-6, gaps(h)
assert abs(h[-1][0] - h[0][0] - 45.0) < 1e-6

# --- speed independence: 2x speed, same span (the Godot property) ---
sim2 = run(dist_em(), 200, 2.0)
h2 = sim2.trail_hist[1]
assert len(h2) == 10, len(h2)
for g in gaps(h2):
    assert abs(g - 5.0) < 1e-6, gaps(h2)
assert abs(h2[-1][0] - h2[0][0] - 45.0) < 1e-6
print("TRAILS-FLOW-DISTANCE-OK")

# --- stopped emitter: trail frozen, never blobs ---
sim3 = SimEngine()
em3 = dist_em()
x = 0.0
for _ in range(200):
    x += 1.0
    sim3.update_trails(em3, [(1, x, 0.0, 0.0)], 0.0, 0.0, 0.0, DT)
frozen = list(sim3.trail_hist[1])
for _ in range(60):
    sim3.update_trails(em3, [(1, x, 0.0, 0.0)], 0.0, 0.0, 0.0, DT)
assert list(sim3.trail_hist[1]) == frozen
print("TRAILS-FLOW-FROZEN-OK")

# --- sectionLength 0: every frame (Trail2D-tick FIFO) ---
sim4 = run(dist_em(sectionLength=0.0), 30, 0.5)
assert len(sim4.trail_hist[1]) == 10, len(sim4.trail_hist[1])
print("TRAILS-FLOW-TICK-OK")

# --- dead particle: trail dies with it (both modes) ---
sim5 = run(dist_em(), 50, 1.0)
sim5.update_trails(dist_em(), [], 0.0, 0.0, 0.0, DT)
assert 1 not in sim5.trail_hist
emT = PS.default_emitter("2d")
emT["trails"].update({"enabled": True, "minTime": 0.0, "minDist": 0.0,
                      "lifetime": 1.0})
sim6 = SimEngine()
for _ in range(10):
    sim6.update_trails(emT, [(1, 1.0, 0.0, 0.0)], 0.0, 0.0, 0.0, DT)
assert 1 in sim6.trail_hist
sim6.update_trails(emT, [], 0.0, 0.0, 0.0, DT)
assert 1 not in sim6.trail_hist
print("TRAILS-FLOW-DEATH-OK")

# --- time mode unchanged: lifetime expiry still bounds the trail ---
sim7 = SimEngine()
em7 = PS.default_emitter("2d")
em7["trails"].update({"enabled": True, "minTime": 0.0, "minDist": 0.0,
                      "lifetime": 0.1, "maxPoints": 512})
for _ in range(60):
    sim7.update_trails(em7, [(1, 1.0, 0.0, 0.0)], 0.0, 0.0, 0.0, DT)
n = len(sim7.trail_hist[1])
assert 0 < n <= 8, n  # 0.1s @60fps ~= 6 alive; 60 without expiry
print("TRAILS-FLOW-TIME-OK n=%d" % n)

# --- emitter source obeys distance mode too ---
sim8 = SimEngine()
em8 = dist_em(source="emitter")
ex = 0.0
for _ in range(200):
    ex += 1.0
    sim8.update_trails(em8, [], ex, 0.0, 0.0, DT)
he = sim8.trail_hist["emitter"]
assert len(he) == 10, len(he)
for g in gaps(he):
    assert abs(g - 5.0) < 1e-6, gaps(he)
print("TRAILS-FLOW-EMITTER-OK")

print("TRAILS-FLOW-OK")
