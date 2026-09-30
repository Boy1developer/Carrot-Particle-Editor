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
    # seed box round-trips into the effect + export (v1.1)
    dpg.set_value("em_seed", 4242)
    S.cb_em_seed("em_seed", 4242)
    assert S.APP.em.get("seed") == 4242
    eff = S.APP.current_effect()
    assert eff["emitter"].get("seed") == 4242
    assert eff["version"] == "1.1"
    assert PS.validate_effect(eff) == []
    # fields widgets round-trip into the effect + export
    dpg.set_value("em_turb", 60.0)
    S.cb_em_float(("fields", "turbulence", "amount"))("em_turb", 60.0)
    dpg.set_value("em_vortex", 30.0)
    S.cb_em_float(("fields", "vortex", "strength"))("em_vortex", 30.0)
    eff = S.APP.current_effect()
    assert eff["emitter"]["fields"]["turbulence"]["amount"] == 60.0
    assert eff["emitter"]["fields"]["vortex"]["strength"] == 30.0
    assert eff["emitter"]["fields"]["collision"]["planeY"] is None
    assert PS.validate_effect(eff) == []
    assert PS.validate_against_schema(eff) == []
    dpg.set_value("em_plane_on", True)
    S.cb_field_plane_toggle("em_plane_on", True)
    eff = S.APP.current_effect()
    assert eff["emitter"]["fields"]["collision"]["planeY"] == 300.0
    assert PS.validate_against_schema(eff) == []
    # export round-trip through the dialog-free write/load path
    import json as _json
    import os as _os
    import tempfile as _tf
    _tmp = _os.path.join(_tf.mkdtemp(prefix="carrot_export_"), "roundtrip.json")
    _old_fp = S.APP.filepath
    try:
        assert S._write_path(_tmp) == _tmp
        assert _os.path.isfile(_tmp)
        with open(_tmp, encoding="utf-8") as _f:
            _back = _json.load(_f)
        assert PS.validate_effect(_back) == []
        _mig, _warns = PS.migrate_effect(_back)
        S._load_path(_tmp)
        assert S.APP.filepath == _tmp
    finally:
        S.APP.filepath = _old_fp
    print("UI-BUILD-OK")
finally:
    dpg.destroy_context()
