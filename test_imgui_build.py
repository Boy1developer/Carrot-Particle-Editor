# Headless UI-build test: constructs every widget, syncs state.
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import studio_imgui as S

    S.apply_theme()
    S.build_ui()
    S.APP.sync_all()
    S.set_type("3d", commit=False)
    S.APP.sync_all()
    S.set_type("2d", commit=False)
    S.APP.sync_all()
    S.select_state(1)
    S.apply_template("Fire")
    # one Shirtless frame of viewport math (no draw): projection sanity
    x, y, sc, d = S.APP.proj(10, 20, 30, 400, 312)
    assert abs(x - 400) > 0 and sc > 0
    print("UI-BUILD-OK")
finally:
    dpg.destroy_context()
