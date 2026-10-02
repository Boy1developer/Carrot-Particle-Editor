# -*- coding: utf-8 -*-
"""Trail templates registry (C++): load all 27, search, apply, validation."""
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "editor"))
import particle_core as C
import particle_studio as PS

schema = [{"key": f["key"], "type": f["type"],
           "min": f.get("min", 0), "max": f.get("max", 1),
           "items": list(f.get("items", []))} for f in PS.TRAIL_SCHEMA]
assert C.templates_init(schema, tempfile.gettempdir()) == 77

# 1) all builtin templates load with zero warnings
files = sorted(glob.glob(os.path.join(
    ROOT, "assets", "presets", "trails", "*", "*.json")))
assert len(files) == 27, len(files)
for p in files:
    tid = os.path.splitext(os.path.basename(p))[0]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    w = C.templates_register(tid, data, False)
    assert w is None, (tid, w)

# 2) category counts: 5/6/5/6/5
expect = {"combat": 5, "magic": 6, "movement": 5, "nature": 6,
          "stylized": 5}
for cat, n in expect.items():
    got = C.templates_list(cat, "", "2d", "name", False)
    assert len(got) == n, (cat, got)
assert len(C.templates_list("", "", "", "name", False)) == 27

# 3) search: name + tag
assert "sword_slash" in C.templates_list("combat", "sword", "2d",
                                         "name", False)
assert "wand_sparkle" in C.templates_list("", "sparkle", "2d",
                                          "name", False)
assert "fire_trail" in C.templates_list("", "fire", "2d", "name", False)

# 4) apply: empty template -> no changes; partial -> exact changed ids
C.templates_register("t_empty", {"settings": {}}, False)
nd, ch = C.templates_apply("t_empty", "2d", PS.default_trails(),
                           PS.default_trails())
assert ch == [], ch
assert sorted(nd) == sorted(PS.default_trails()), "merge must be complete"
C.templates_register("t_two", {"settings": {"lifetime": 0.25,
                                            "maxPoints": 99}}, False)
nd, ch = C.templates_apply("t_two", "2d", PS.default_trails(),
                           PS.default_trails())
assert sorted(ch) == ["lifetime", "maxPoints"], ch
assert nd["lifetime"] == 0.25 and nd["maxPoints"] == 99

# 5) validation: bad values warn + drop, unknown keys dropped silently
w = C.templates_register("t_bad", {"settings": {"lifetime": "x",
                                                "space": "bogus",
                                                "zzz_unknown": 1}}, False)
assert w and "lifetime" in w and "space" in w, w
nd, _ch = C.templates_apply("t_bad", "2d", PS.default_trails(),
                            PS.default_trails())
assert nd["lifetime"] == PS.default_trails()["lifetime"]
assert nd["space"] == PS.default_trails()["space"]

# 6) thumbnails + procedural textures sized correctly
w, h, buf = C.templates_thumbnail("sword_slash", 96, 48)
assert (w, h) == (96, 48) and len(buf) == 96 * 48 * 4
w, h, buf = C.templates_texture("flame", 64, 64)
assert (w, h) == (64, 64) and len(buf) == 64 * 64 * 4
w2, h2, buf2 = C.templates_texture("flame", 64, 64)
assert bytes(buf) == bytes(buf2), "texture cache must be deterministic"

# 7) user preset save/delete roundtrip (isolated temp dir)
with tempfile.TemporaryDirectory() as td:
    C.templates_init(schema, td)
    for p in files:  # re-register after init cleared the registry
        tid = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            C.templates_register(tid, json.load(f), False)
    cur = PS.default_trails()
    cur["lifetime"] = 1.23
    path = C.presets_save("my_test", cur, {"name": "My Test"})
    assert os.path.isfile(path), path
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["settings"]["lifetime"] == 1.23
    C.templates_register("my_test", saved, True)
    assert "my_test" in C.templates_list("user", "", "2d", "name", False)
    C.presets_delete("my_test")
    assert not os.path.isfile(path)
    assert "my_test" not in C.templates_list("user", "", "2d",
                                             "name", False)

# 8) fallback parity: pure-Python merge == C++ merge for every template
def _py_fallback_merge(data, mode, defaults):
    merged = PS.sanitize_trails(dict(defaults))
    for k in list(merged):
        if k in data.get("settings", {}):
            merged[k] = data["settings"][k]
        ov = data.get("overrides_3d" if mode == "3d" else "overrides_2d",
                      {})
        if k in ov:
            merged[k] = ov[k]
    return PS.sanitize_trails(merged)


def _norm(v):
    return json.dumps(v, sort_keys=True)


def _canon_keylist(rows):
    """Canonical form: [float(x), y, mode] (C++ normalizes 2-elem rows)."""
    out = []
    for r in rows or []:
        x = float(r[0])
        y = r[1]
        if isinstance(y, (int, float)):
            y = float(y)
        m = r[2] if len(r) > 2 else "smooth"
        out.append([x, y, m])
    return sorted(out, key=lambda r: r[0])


def _norm_trails(t):
    t = dict(t)
    for k in ("widthCurve", "colorStops", "alphaStops", "lifeColorStops",
              "lifeAlphaStops"):
        if k in t and isinstance(t[k], list):
            t[k] = _canon_keylist(t[k])
    return json.dumps(t, sort_keys=True)


d0 = PS.default_trails()
for p in files:
    tid = os.path.splitext(os.path.basename(p))[0]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    for mode in ("2d", "3d"):
        nd, _ch = C.templates_apply(tid, mode, d0, d0)
        py = _py_fallback_merge(data, mode, d0)
        assert _norm_trails(nd) == _norm_trails(py), (tid, mode)
print("TRAILS-TEMPLATES-FALLBACK-PARITY-OK")

# 9) apply-every-template + step-simulation smoke (catches crashes);
#     template output also feeds the C++ TrailCfg LUT path bit-exactly
TRACKS = [
    {"dur": 0.5, "shape": "circle", "size": 8, "sizeMax": 12,
     "color": "#ffaa00", "opacity": 255, "minSpeed": 60, "maxSpeed": 160,
     "easing": "linear"},
    {"dur": 0.5, "shape": "circle", "size": 2, "sizeMax": 4,
     "color": "#ff3300", "opacity": 0, "minSpeed": 20, "maxSpeed": 60,
     "easing": "ease-out"},
]
for p in files:
    tid = os.path.splitext(os.path.basename(p))[0]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    modes = data.get("modes", ["2d", "3d"])
    for mode in modes:
        nd, _ch = C.templates_apply(tid, mode, d0, d0)
        # complete + in-range + no NaN/empty-gradients (== exporter-ready)
        assert sorted(nd) == sorted(d0), tid
        for f in PS.TRAIL_SCHEMA:
            v = nd[f["key"]]
            if f["type"] == "float":
                assert v == v and f.get("min", -1e9) - 1e-9 <= v <= f.get(
                    "max", 1e9) + 1e-9, (tid, f["key"], v)
            if f["type"] in ("curve", "gradient-color", "gradient-alpha"):
                assert isinstance(v, list) and len(v) > 0, (tid, f["key"])
        em = dict(PS.default_emitter(), trails=nd)
        e = C.Engine()
        e.configure(em, TRACKS, mode == "3d")
        for _i in range(30):
            e.step(1.0 / 60.0, 400, 300, 0, 0, 0, 0, 0, 0, 500,
                   0.7, 0.42, 1.0, 0, 0, 620, 400, 300)
        t = e.trails_luts()
        assert len(t["w"]) == 64 and len(t["r"]) == 256, tid
print("TRAILS-TEMPLATES-SIM-SMOKE-OK")

# 10) template -> LUT parity on curve/gradient/texture representatives
for tid, mode in (("neon_paint", "2d"), ("rainbow_ribbon", "2d"),
                  ("energy_beam", "3d")):
    nd, _ch = C.templates_apply(tid, mode, d0, d0)
    em = dict(PS.default_emitter(), trails=nd)
    e = C.Engine()
    e.configure(em, TRACKS, mode == "3d")
    t = e.trails_luts()
    py_w = PS.bake_curve(nd["widthCurve"])
    assert all(abs(a - b) < 1e-9 for a, b in zip(t["w"], py_w)), tid
    py_c = PS.bake_gradient(nd["colorStops"], nd["alphaStops"])
    for i, px in enumerate(py_c):
        assert tuple(px) == (t["r"][i], t["g"][i], t["b"][i],
                             t["a"][i]), (tid, i)
print("TRAILS-TEMPLATES-LUT-PARITY-OK")

# 11) perf budgets: scan+validate < 20ms, apply < 1ms, filter < 0.5ms
import time as _t
t0 = _t.time()
for p in files:
    tid = os.path.splitext(os.path.basename(p))[0]
    with open(p, encoding="utf-8") as f:
        C.templates_register(tid, json.load(f), False)
scan_ms = (_t.time() - t0) * 1000.0
t0 = _t.time()
for tid in C.templates_list("", "", "", "name", False):
    C.templates_apply(tid, "2d", d0, d0)
apply_ms = (_t.time() - t0) / 27 * 1000.0
t0 = _t.time()
for _i in range(50):
    C.templates_list("", "fire", "2d", "name", False)
filt_ms = (_t.time() - t0) / 50 * 1000.0
print("TRAILS-TEMPLATES-PERF scan=%.2fms apply=%.3fms filter=%.3fms"
      % (scan_ms, apply_ms, filt_ms))
assert scan_ms < 20.0, scan_ms
assert apply_ms < 1.0, apply_ms
assert filt_ms < 0.5, filt_ms

# 12) art-direction recipes: full look per template, never uniform
DEMOS = {"arc_swing", "overhead_swing", "straight_shot",
         "parabolic_flight", "dash_stop_go", "figure8", "sweep_ease",
         "teleport_zigzag", "sine", "ellipse_orbit", "wobble_line",
         "s_curve_ground", "long_sweep", "lazy_sine", "torch_swing",
         "fountain_arc", "swirl_loop", "straight_slide",
         "draw_and_hold", "wave", "static_center"}
docs = {}
for p in files:
    with open(p, encoding="utf-8") as f:
        docs[os.path.splitext(os.path.basename(p))[0]] = json.load(f)
assert len(docs) == 27
for tid, d in docs.items():
    assert str(d.get("artNotes") or "").strip(), tid
    assert d.get("demoMotion") in DEMOS, (tid, d.get("demoMotion"))
    st = d.get("settings", {})
    assert st.get("enabled") is True, tid
    nd, _ch = C.templates_apply(tid, "2d", d0, d0)
    assert sorted(nd) == sorted(d0), (tid, "merged look must be complete")
widths = {json.dumps(d["settings"]["widthStart"]) for d in docs.values()}
assert len(widths) >= 8, widths  # silhouettes differ, not one streak
glow = sum(1 for d in docs.values()
           if d["settings"].get("glowWidth", 0) > 0)
core = sum(1 for d in docs.values() if d["settings"].get("coreColor"))
flick = sum(1 for d in docs.values()
            if d["settings"].get("flickerAmt", 0) > 0)
hybrid = sum(1 for d in docs.values()
             if d["settings"].get("hideParticle") is False)
assert glow >= 5 and core >= 3 and flick >= 1 and hybrid >= 3, (
    glow, core, flick, hybrid)
print("TRAILS-TEMPLATES-ART-OK glow=%d core=%d flick=%d hybrid=%d"
      % (glow, core, flick, hybrid))

print("TRAILS-TEMPLATES-OK")
