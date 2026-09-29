# Shape morph: birth shape cross-fades into death shape inside the
# flip window (raw segment time in (0.25, 0.75)), single draw otherwise.
import bootstrap  # tests/ sys.path setup (repo root + editor/)
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import studio_imgui as S

    # 1) blend_window edges
    tr = [{"dur": 0.5, "easing": "linear"}, {"dur": 0.5, "easing": "linear"}]
    assert S.SimEngine.blend_window(tr, 0.0) == (-1, 0.0)
    assert S.SimEngine.blend_window(tr, 0.1) == (-1, 0.0)
    assert S.SimEngine.blend_window(tr, 0.125) == (-1, 0.0)  # raw == 0.25
    bs, t = S.SimEngine.blend_window(tr, 0.2)
    assert bs == 0 and abs(t - 0.3) < 1e-9, (bs, t)
    bs, t = S.SimEngine.blend_window(tr, 0.3)
    assert bs == 0 and abs(t - 0.7) < 1e-9, (bs, t)
    assert S.SimEngine.blend_window(tr, 0.49) == (-1, 0.0)
    assert S.SimEngine.blend_window([{"dur": 0.5}], 0.3) == (-1, 0.0)
    assert S.SimEngine.blend_window([], 0.3) == (-1, 0.0)
    aA, aB = S._split_alpha(0.3)
    assert (aA, aB) == (178, 76), (aA, aB)  # banker's rounding
    assert aA + aB in (254, 255, 256)

    S.build_ui()
    app = S.APP
    app.ptype = "2d"
    import particle_studio as PS
    app.states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
    app.states[0]["shape"] = "circle"
    app.states[1]["shape"] = "square"
    app.sel_state = 0
    app.colormode = "gradient"
    tracks = S.SimEngine._build_tracks(app.states, "2d")

    # 2) 2D C++ path: blend window draws BOTH shapes with split alpha
    seen = []
    real_2d = S.draw_shape_2d
    S.draw_shape_2d = lambda dl, x, y, r, shape, col, *a, **k: seen.append(
        (shape, list(col)))
    try:
        n = 3
        out = {"x": [10.0] * n, "y": [20.0] * n, "r": [5.0] * n,
               "color": [0xFFAA00] * n,
               "shape": [PS.SHAPE_ORDER.index("circle")] * n,
               "depth": [0.0] * n,
               "bseg": [0, -1, -1], "bt": [0.3, 0.0, 0.0]}
        app.sim._cpp_out = out
        S.draw_view_2d(app, "vp_draw", 800, 600, 400, 312, None, tracks)
    finally:
        S.draw_shape_2d = real_2d
        app.sim._cpp_out = None
    assert len(seen) == 4, seen  # 2 (blend) + 1 + 1
    assert seen[0][0] == "circle" and seen[1][0] == "square", seen
    assert seen[0][1][3] > seen[1][1][3]  # A dominates at t=0.3
    assert seen[0][1][3] + seen[1][1][3] in (254, 255, 256)
    assert seen[2][0] == "circle" and seen[3][0] == "circle"

    # 3) legacy out dict without blend keys: single draws, no crash
    seen.clear()
    S.draw_shape_2d = lambda dl, x, y, r, shape, col, *a, **k: seen.append(
        (shape, list(col)))
    try:
        out2 = {"x": [10.0], "y": [20.0], "r": [5.0], "color": [0xFFAA00],
                "shape": [PS.SHAPE_ORDER.index("circle")], "depth": [0.0]}
        app.sim._cpp_out = out2
        S.draw_view_2d(app, "vp_draw", 800, 600, 400, 312, None, tracks)
    finally:
        S.draw_shape_2d = real_2d
        app.sim._cpp_out = None
    assert len(seen) == 1 and seen[0][1][3] == 255, seen

    # 4) 3D py-fallback path: fabricated part inside the window morphs
    app.ptype = "3d"
    app.states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
    app.states[0]["shape"] = "sphere"
    app.states[1]["shape"] = "cube"
    tr3 = S.SimEngine._build_tracks(app.states, "3d")
    # part layout: [x,y,vx,vy,age,...life(9),z(10),vz,shape(12),tracks(13),
    #               dx,dy,dz,gx,gy,gz,sizeRatio(20),speedRatio(21)]
    p = [0.0] * 22
    p[4] = 0.2  # age -> raw 0.4 on the 0.5s birth segment
    p[9] = 1.0
    p[12] = "sphere"
    p[13] = tr3
    p[20] = 0.5
    p[21] = 0.5
    app.sim.parts = [p]
    app.sim._cpp_out = None
    seen3 = []
    real_3d = S.draw_shape_3d
    S.draw_shape_3d = lambda dl, x, y, r, shape, col, *a, **k: seen3.append(
        (shape, list(col)))
    try:
        em = {"emissionZone": {"showZone": False},
              "propagationCone": {"showCone": False}}
        S.draw_view_3d(app, "vp_draw", 800, 600, 400, 312, em, tr3)
    finally:
        S.draw_shape_3d = real_3d
        app.sim.parts = []
    shapes = [s for s, _c in seen3]
    assert "sphere" in shapes and "cube" in shapes, seen3
    print("MORPH-OK")
finally:
    dpg.destroy_context()
