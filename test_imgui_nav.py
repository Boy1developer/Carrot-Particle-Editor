# Headless nav test: wheel-anchor zoom, focus, WASD math.
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import studio_imgui as S

    S.build_ui()
    S.choose("2d")
    app = S.APP
    ox0, oy0, z0 = app.cam["ox"], app.cam["oy"], app.cam["zoom"]
    # wheel zoom anchored at cursor (lx,ly)=(500,300), center (400,300)
    app._wheel = 1.0
    S.handle_mouse(500, 300, True, 800, 600, 400, 312)
    assert app.cam["zoom"] > z0, app.cam["zoom"]
    # world point under cursor stays: (lx-cx-ox)/zoom invariant
    before = (500 - 400 - ox0) / z0
    after = (500 - 400 - app.cam["ox"]) / app.cam["zoom"]
    assert abs(before - after) < 1e-6, (before, after)
    # focus emitter centers it
    app.emitter2d = [50.0, -30.0]
    W, H, cx, cy = 800, 600, 400, 312.0
    S.focus_emitter(W, H, cx, cy)
    ex = cx + app.cam["ox"] + app.emitter2d[0]
    ey = cy + app.cam["oy"] + app.emitter2d[1]
    assert abs(ex - cx) < 1e-6 and abs(ey - cy) < 1e-6, (ex, ey)
    # nav guarded while typing
    assert S._typing() is False
    print("NAV-OK")
finally:
    dpg.destroy_context()
