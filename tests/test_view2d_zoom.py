# -*- coding: utf-8 -*-
"""2D view transform: world-space sim + zoom-anchored projection."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "editor"))
import particle_studio as PS

from studio_imgui import SimEngine, view2d, view2d_inv  # noqa: E402

# --- identity at rest (legacy pixels preserved) ---
assert view2d(10.0, -5.0, 450.0, 320.0, 0.0, 0.0, 1.0) == (460.0, 315.0)
# --- pan + zoom ---
sx, sy = view2d(100.0, 50.0, 450.0, 320.0, 30.0, -20.0, 2.0)
assert (sx, sy) == (450.0 + 30.0 + 200.0, 320.0 - 20.0 + 100.0)
# --- inverse round-trips (gizmo drags) ---
for w in ((0.0, 0.0), (123.5, -77.25), (-400.0, 900.0)):
    s = view2d(w[0], w[1], 450.0, 320.0, 30.0, -20.0, 2.5)
    b = view2d_inv(s[0], s[1], 450.0, 320.0, 30.0, -20.0, 2.5)
    assert abs(b[0] - w[0]) < 1e-9 and abs(b[1] - w[1]) < 1e-9, (w, b)
print("VIEW2D-MATH-OK")


def anchored_ox(ox, m_minus_cx, s):
    """Shared pivot formula (wheel at cursor, Q/E at viewport center)."""
    return m_minus_cx - (m_minus_cx - ox) * s


# --- wheel anchor: world under the cursor never moves ---
cx, ox, z, lx = 450.0, 30.0, 1.0, 600.0
s = 1.5
ox2 = anchored_ox(ox, lx - cx, s)
w_before = (lx - cx - ox) / z
w_after = (lx - cx - ox2) / (z * s)
assert abs(w_before - w_after) < 1e-9, (w_before, w_after)
# --- Q/E anchor: viewport center stays put ---
W, H = 900.0, 640.0
ox3 = anchored_ox(ox, W / 2 - cx, s)
assert abs((W / 2 - cx - ox3) / (z * s)
           - (W / 2 - cx - ox) / z) < 1e-9
print("VIEW2D-ANCHOR-OK")

# --- spawn stores WORLD coords (pan/zoom independent), not screen ---
eng = SimEngine()
em2d = PS.default_emitter("2d")
states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
tr = SimEngine._build_tracks(states, "2d")
p = eng.spawn(em2d, "2d", 0.0, 0.0, (0, 0, 0), tr)
assert abs(p[0]) <= 60.0 and abs(p[1]) <= 60.0, p[:2]  # zone-sized, not 400s
# reverse mode offsets from the world emitter too
emR = dict(em2d, reverse=True)
pr = eng.spawn(emR, "2d", 5.0, -5.0, (0, 0, 0), tr)
assert abs(pr[0] - 5.0) > 20.0 and abs(pr[1] + 5.0) > 20.0, pr[:2]
print("VIEW2D-SPAWN-OK")

# --- emitter-trail anchor follows the world emitter (not screen/origin)
emT = PS.default_emitter("2d")
emT["trails"].update({"enabled": True, "source": "emitter",
                      "maxPoints": 64, "minDist": 0.0, "minTime": 0.0})
sim = SimEngine()
for i in range(5):
    sim.step_py(emT, "2d", 7.0, -3.0, (0, 0, 0),
                {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0, "ox": 999.0,
                 "oy": 999.0, "focal": 620.0},
                SimEngine._build_tracks(states, "2d"), 1 / 60, 800)
h = sim.trail_hist.get("emitter", [])
assert h and all(abs(x - 7.0) < 1e-9 and abs(y + 3.0) < 1e-9
                 for (x, y, _z, _t) in h), h[:2]
print("VIEW2D-ANCHOR-TRAIL-OK")

# --- raster layer agrees with the vector layer (same view transform) ---
import raster_view as RV

out = {"x": [100.0, -50.0], "y": [20.0, 0.0], "z": [0.0, 0.0],
       "r": [4.0, 8.0], "color": [0xFF0000, 0x00FF00], "shape": [0, 0]}
W, H, cx, cy, ox, oy, z = 900.0, 640.0, 450.0, 332.8, 30.0, -20.0, 2.0
k = 320 / W
buckets, _glow = RV._scale_split(PS, out, k, ox, oy, z, W * 0.5, H * 0.52)
pts = buckets["circle"]
for (rx, ry, _zz, rr, _c1, _c2, _c3, _a), wx, wy in zip(
        pts, out["x"], out["y"]):
    vx, vy = view2d(wx, wy, cx, cy, ox, oy, z)
    assert abs(rx / k - vx) < 1e-9 and abs(ry / k - vy) < 1e-9, (rx, vx)
assert abs(pts[0][3] - max(1.0, 4.0 * z) * k) < 1e-9, pts[0][3]
print("VIEW2D-RASTER-OK")

print("VIEW2D-ZOOM-OK")
