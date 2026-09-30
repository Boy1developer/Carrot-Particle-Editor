# Headless UI-build test: constructs every widget, syncs state.
import bootstrap  # tests/ sys.path setup (repo root + editor/)
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
    # per-emitter blend dropdown round-trips into the effect + export
    import particle_studio as PS
    assert dpg.get_item_configuration("em_blend")["items"] == PS.BLEND_MODES
    dpg.set_value("em_blend", "Screen")
    S.cb_em_combo(("blendingMode",))("em_blend", "Screen")
    assert S.APP.em.get("blendingMode") == "Screen"
    eff = S.APP.current_effect()
    assert eff["emitter"].get("blendingMode") == "Screen"
    assert PS.validate_effect(eff) == []
    assert PS.validate_against_schema(eff) == []
    print("UI-BUILD-OK")
finally:
    dpg.destroy_context()
