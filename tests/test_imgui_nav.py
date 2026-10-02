# Headless nav test: wheel-anchor zoom, focus, WASD math.
import bootstrap  # tests/ sys.path setup (repo root + editor/)
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
    # focus emitter centers it (zoom-aware view transform)
    app.emitter2d = [50.0, -30.0]
    W, H, cx, cy = 800, 600, 400, 312.0
    S.focus_emitter(W, H, cx, cy)
    ex, ey = S.view2d(app.emitter2d[0], app.emitter2d[1], cx, cy,
                      app.cam["ox"], app.cam["oy"], app.cam["zoom"])
    assert abs(ex - cx) < 1e-6 and abs(ey - cy) < 1e-6, (ex, ey)
    # nav guarded while typing
    assert S._typing() is False
    # type switch rebuilds a type-correct emitter (no 2D leak into 3D)
    S.set_type("3d", commit=False)
    eff3 = app.current_effect()
    assert "directionZ" in eff3["emitter"]["propagationCone"], \
        eff3["emitter"]["propagationCone"]
    assert eff3["emitter"]["emissionZone"]["shape"] in ("sphere", "box",
                                                        "point", "line")
    tr3 = S.SimEngine._build_tracks(app.states, "3d")
    p3 = S.SimEngine().spawn(eff3["emitter"], "3d", 400, 312, (0, 0, 0),
                             tr3)
    assert len(p3) == 22
    S.set_type("2d", commit=False)
    eff2 = app.current_effect()
    assert "direction" in eff2["emitter"]["propagationCone"]
    assert "directionZ" not in eff2["emitter"]["propagationCone"]
    # splitter hover math (drag needs a real pressed button)
    assert S.handle_splitter(3.0, True) is False
    assert app._split_hover is True
    assert S.handle_splitter(500.0, False) is False
    assert app._split_hover is False
    assert app.side_w == 320
    print("NAV-OK")
finally:
    dpg.destroy_context()
