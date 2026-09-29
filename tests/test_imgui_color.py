# Repro: user picks teal on birth, switches states.
# Widget must ALWAYS show the selected state's real color (no global override).
import bootstrap  # tests/ sys.path setup (repo root + editor/)
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import studio_imgui as S

    S.apply_theme()
    S.build_ui()
    S.APP.sync_all()
    app = S.APP
    print("HAS_CPP:", S.HAS_CPP_CORE)

    # 1) user picks teal via color widget on birth (sel=0)
    app.sel_state = 0
    S.cb_color_edit("st_color_edit", [0, 255, 164, 255])
    print("after edit birth:", app.states[0]["appearance"].get("color"),
          "op:", app.states[0]["appearance"].get("opacity"))
    assert app.states[0]["appearance"]["color"] == "#00ffa4"
    assert app.states[0]["appearance"]["opacity"] == 255

    # 2) switch to death -> widget must show DEATH's real color
    S.select_state(1)
    whex = dpg.get_value("st_color_hex")
    print("on death: widget hex:", whex,
          "| state color:", app.states[1]["appearance"].get("color"))
    assert whex == app.states[1]["appearance"]["color"] == "#ff3300", whex

    # 3) recolor death magenta, switch back and forth, widget==state always
    S.cb_color_edit("st_color_edit", [255, 0, 255, 255])
    assert app.states[1]["appearance"]["color"] == "#ff00ff"
    assert app.states[1]["appearance"]["opacity"] == 255
    # 3b) hostile payloads must never corrupt the state
    S.select_state(0)
    S.cb_color_edit("st_color_edit", None)  # DPG zero-arg call: widget fallback
    assert app.states[0]["appearance"]["color"] == "#00ffa4", \
        app.states[0]["appearance"]
    S.cb_color_edit("st_color_edit", [0.0, 1.0, 0.64])  # normalized floats
    assert app.states[0]["appearance"]["color"] == "#00ffa3", \
        app.states[0]["appearance"]
    S.cb_color_edit("st_color_edit", [0, 255, 164, 255])  # restore teal
    S.cb_color_hex("st_color_hex", "00ff00")  # missing '#' tolerated
    assert app.states[0]["appearance"]["color"] == "#00ff00", \
        app.states[0]["appearance"]
    S.cb_color_hex("st_color_hex", "notacolor")  # garbage ignored
    assert app.states[0]["appearance"]["color"] == "#00ff00"
    S.cb_color_edit("st_color_edit", [0, 255, 164, 255])  # restore teal
    S.select_state(0)
    assert dpg.get_value("st_color_hex") == "#00ffa4", \
        dpg.get_value("st_color_hex")
    S.select_state(1)
    assert dpg.get_value("st_color_hex") == "#ff00ff", \
        dpg.get_value("st_color_hex")
    print("widget==state on every switch: OK")

    # 4) viewport pipeline: tracks + C++ engine young-particle colors
    S.select_state(0)
    tracks = S.SimEngine._build_tracks(app.states, app.ptype)
    print("tracks colors:", [(t["color"], t["opacity"]) for t in tracks])
    assert tracks[0]["color"] == "#00ffa4"
    if S.HAS_CPP_CORE:
        import particle_core as C
        eng = C.Engine()
        eng.set_seed(123)
        em = app.read_emitter()
        eng.configure(em, tracks, False)
        out = None
        for _ in range(40):
            out = eng.step(1 / 60.0, 400, 312, 0, 0, 0, 0, 0, 0, 300,
                           0.7, 0.42, 1.0, 0, 0, 620.0, 400, 312)
        cols = out["color"]
        print("n:", len(cols),
              "min: %06x" % min(cols), "max: %06x" % max(cols))
        tealish = [c for c in cols
                   if ((c >> 16) & 255) < 120 and ((c >> 8) & 255) > 150]
        black = [c for c in cols if c == 0]
        print("tealish:", len(tealish), "black:", len(black))
        assert tealish, "NO teal particles after birth=teal!"
        assert not black, f"BLACK particles present: {len(black)}"
    print("REPRO-OK")
finally:
    dpg.destroy_context()
