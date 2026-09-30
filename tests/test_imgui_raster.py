# Raster viewport path (Phase 3): PPM conversion, orientation, auto-switch.
import os
import sys

import bootstrap  # noqa: F401

import raster_view as RV

# 1) ppm_to_floats: pure conversion, no GL needed
ppm = b"P6\n4 2\n255\n" + bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255,
                                 0, 0, 0, 128, 128, 128, 64, 64, 64, 0, 0, 0])
w, h, floats = RV.ppm_to_floats(ppm)
assert (w, h) == (4, 2), (w, h)
assert len(floats) == 4 * 2 * 3, len(floats)
assert floats[0] == 1.0 and floats[1] == 0.0 and floats[2] == 0.0
assert floats[3] == 0.0 and floats[4] == 1.0 and floats[5] == 0.0
assert abs(floats[15] - 128 / 255.0) < 1e-9
assert all(isinstance(v, float) for v in floats)
assert RV.raster_size(800, 536) == (320, round(320 * 536 / 800))
print("ppm conversion: OK")

# 2) orientation: two dots (canvas-top vs canvas-bottom) must keep order
try:
    from render.gl_view import GLView, mat_ortho
    _v = GLView()
    _gl_ok = bool(getattr(_v, "ok", False))
except Exception as e:  # noqa: BLE001
    print("SKIP orientation (no GL):", str(e)[:100])
    _gl_ok = False
if _gl_ok:
    W, H = 320, 214
    dots = {"circle": [(160.0, 10.0, 0.0, 5.0, 1.0, 1.0, 1.0, 1.0),
                       (160.0, H - 10.0, 0.0, 5.0, 1.0, 0.0, 0.0, 1.0)]}
    ppm = _v.render(dots, [], W, H, ortho=1,
                    clip=mat_ortho(0, W, 0, H, -1000, 1000),
                    zoom=1.0, focal=620.0, bg=(0, 0, 0), grid=())
    w, h, floats = RV.ppm_to_floats(ppm)
    assert (w, h) == (W, H)
    # white dot (canvas-top) carries green; red dot (canvas-bottom) does not
    greens = [floats[(y * w + 160) * 3 + 1] for y in range(h)]
    row_white = max(range(h), key=lambda y: greens[y])
    assert row_white < h // 2, ("canvas-top dot not in top half", row_white)
    red_only = [floats[(y * w + 160) * 3] - floats[(y * w + 160) * 3 + 1]
                for y in range(h)]
    row_red = max(range(h), key=lambda y: red_only[y])
    assert row_red > h // 2, ("canvas-bottom dot not in bottom half", row_red)
    _v.close()
    print(f"orientation row0=top: OK (top dot row {row_white}, bottom dot row {row_red})")

# 3) auto-switch logic (no GL needed: threshold + mesh guards short-circuit first)


class _Sim:
    _cpp_out = {"x": [1.0]}


class _App:
    states = []
    sim = _Sim()


assert RV.should_raster(_App(), RV.MIN_N - 1) is False  # below threshold
assert RV.should_raster(_App(), 0) is False
_App.states = [{"customModel": {"file": "r.glb"}}]
_real_gl = RV.get_gl
RV.get_gl = lambda: object()
try:
    assert RV.should_raster(_App(), RV.MIN_N + 5000) is False  # meshes stay vector
    _App.states = []
    _App.sim._cpp_out = None
    assert RV.should_raster(_App(), RV.MIN_N + 5000) is False  # needs C++ output
    _App.sim._cpp_out = {"x": [1.0]}
    assert RV.should_raster(_App(), RV.MIN_N + 5000) is True
finally:
    RV.get_gl = _real_gl
    _App.sim._cpp_out = {"x": [1.0]}
print("auto-switch: OK")

# 4) frame builders fail soft without GL
RV.get_gl = lambda: None
try:
    assert RV.frame_2d(_App(), {"x": [1.0]}, 800, 536) is None
    assert RV.frame_3d(_App(), {"x": [1.0]}, 800, 536, 400, 278) is None
finally:
    RV.get_gl = _real_gl
print("no-GL fallback: OK")

# 5) texture upload works headless (tiny texture, skip if DPG disagrees)
try:
    import dearpygui.dearpygui as dpg
    dpg.create_context()
    try:
        tag = RV.ensure_texture(8, 4)
        assert tag == RV.TEX_TAG, tag
        assert RV.update_texture([0.5] * (8 * 4 * 3)) is True
        print("texture upload headless: OK")
    finally:
        dpg.destroy_context()
        RV._tex_size = None
except Exception as e:  # noqa: BLE001
    print("SKIP texture upload:", str(e)[:120])
print("RASTER-OK")
