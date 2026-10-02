# -*- coding: utf-8 -*-
"""Ribbon-strip renderer math (pure) + headless DPG paint smoke."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "editor"))
import trail_render as TR

# --- style defaults (old blocks identical: hide dots, 2.5px floor) ---
s = TR.resolve_style({})
assert s["minScreenWidth"] == 2.5 and s["hideParticle"] is True
assert s["glowWidth"] == 0.0 and s["glowAlpha"] == 0.0
assert s["flickerAmt"] == 0.0 and s["coreWidth"] == 0.35

# --- width profile: lerp * curve * mult, tapers pinch the ends ---
wlut = [1.0] * 64
st = dict(s, widthStart=10.0, widthEnd=2.0, widthMult=2.0,
          taperHead=False, taperTail=False)
assert abs(TR.width_at(0.0, st, wlut) - 20.0) < 1e-9
assert abs(TR.width_at(1.0, st, wlut) - 4.0) < 1e-9
st2 = dict(st, taperHead=True, taperTail=True)
assert TR.width_at(0.0, st2, wlut) == 0.0
assert TR.width_at(1.0, st2, wlut) == 0.0
assert TR.width_at(0.5, st2, wlut) > 0.0
# floor: no hairlines ever
assert TR.floored_width(1.0, st, wlut) == 4.0
st3 = dict(st, widthStart=0.0, widthEnd=0.0)
assert TR.floored_width(0.5, st3, wlut) == 2.5

# --- gradient sampling clamps ---
import particle_studio as _PS
grad = _PS.bake_gradient([[0, "#0a141e"], [1, "#32463c"]],
                         [[0, 40], [1, 80]])
assert TR.lut_color(grad, -1.0) == grad[0]
assert TR.lut_color(grad, 2.0) == grad[-1]
assert TR.lut_color([], 0.5) == (255, 255, 255, 255)

# --- color layers ---
assert TR.mix((0, 0, 0), (100, 200, 50), 0.0) == (0, 0, 0)
assert TR.mix((0, 0, 0), (100, 200, 50), 1.0) == (100, 200, 50)
stc = dict(s, hasCore=True, coreColor=(10, 20, 30), intensity=1.0)
assert TR.core_color((200, 200, 200), stc) == (10.0, 20.0, 30.0)
assert TR.core_color((100, 100, 100), s) == (145.0, 145.0, 145.0)
assert TR.outer_alpha(200.0, dict(s, edgeSoftness=0.0)) == 200.0
assert abs(TR.outer_alpha(200.0, dict(s, edgeSoftness=1.0)) - 110.0) < 1e-9

# --- flicker bounds + off switch ---
assert TR.flicker_factor(1.0, 8.0, 0.0, 0.0) == 1.0
for ph in (0.0, 0.25, 0.5, 0.9):
    f = TR.flicker_factor(0.37, 30.0, 0.5, ph)
    assert 0.5 - 1e-9 <= f <= 1.0, (ph, f)

# --- striding: endpoints kept, draw calls bounded ---
assert TR.stride_indices(1) == [0]
assert TR.stride_indices(5) == [0, 1, 2, 3, 4]
idx = TR.stride_indices(200)
assert idx[0] == 0 and idx[-1] == 199 and len(idx) <= TR.MAX_SEGS + 1

# --- ribbon geometry: symmetric offsets, degenerate-safe ---
pts = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
left, right = TR.build_ribbon(pts, [4.0, 4.0, 4.0])
assert left[1] == (10.0, 2.0) and right[1] == (10.0, -2.0)
left2, _right2 = TR.build_ribbon([(5.0, 5.0)], [3.0])
assert len(left2) == 1  # no crash on single point
q = TR.seg_quad(left, right, 0)
assert q == [left[0], right[0], right[1], left[1]]

# --- detail tiers + pre-stride ---
assert TR.detail_for_count(3) == (8, True)
assert TR.detail_for_count(20) == (5, True)
assert TR.detail_for_count(40) == (3, False)
many = [(float(i), 0.0) for i in range(200)]
ps = TR.pre_stride(many)
assert len(ps) <= TR.MAX_INPUT_PTS and ps[0] == many[0] and ps[-1] == many[-1]
assert TR.pre_stride([(1.0, 2.0)]) == [(1.0, 2.0)]

print("TRAILS-RENDER-MATH-OK")

# --- headless DPG smoke: real paint path draws strips + glow ---
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import studio_imgui as S

    tcfg = {"enabled": True, "source": "particles", "maxPoints": 64,
            "lifetime": 2.0, "minDist": 1.0, "smoothing": 2,
            "widthStart": 14.0, "widthEnd": 2.0, "widthMult": 1.5,
            "widthCurve": [[0, 1], [1, 0.1]], "taperTail": True,
            "colorStops": [[0, "#ffffff"], [1, "#1f3fff"]],
            "alphaStops": [[0, 255], [1, 0]],
            "edgeColor": "#55b8ff", "edgeSoftness": 0.6,
            "coreColor": "#ffffff", "coreWidth": 0.35,
            "glowWidth": 2.0, "glowAlpha": 0.35, "intensity": 1.5,
            "minScreenWidth": 2.5}
    S.APP.em["trails"] = dict(tcfg)
    S.rebake_trails_lut()
    S.APP.sim.trail_hist = {
        "p1": [(float(x), 100.0 + 0.5 * x, 0.0, 0.01 * x)
               for x in range(40)],
        "p2": [(float(x), 200.0 - 0.3 * x, 0.0, 0.01 * x)
               for x in range(40)],
    }
    S.APP.trail_dbg = {}
    S.APP._trail_draws = 0
    with dpg.window(tag="__trl_smoke__", show=False):
        with dpg.drawlist(tag="__trl_dl__", width=640, height=480):
            pass
    S.paint_trails_2d(S.APP, "__trl_dl__", {"emitter": {"trails": tcfg}})
    assert S.APP._trail_draws > 4, S.APP._trail_draws  # strips, not 2 lines
    # hybrid gate: dots visible when hideParticle is False
    assert S._hide_trail_particles({"trails": tcfg}) is True
    assert S._hide_trail_particles(
        {"trails": dict(tcfg, hideParticle=False)}) is False
    assert S._hide_trail_particles({}) is True  # old files unchanged
    print("TRAILS-RENDER-SMOKE-OK draws=%d" % S.APP._trail_draws)
finally:
    dpg.destroy_context()
