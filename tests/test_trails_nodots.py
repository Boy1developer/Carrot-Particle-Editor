# -*- coding: utf-8 -*-
"""No template may resurrect particle dots: every trail template applied in
2D or 3D trail mode must land ribbons-only (hideParticle=true + enabled),
so both viewport painters skip paint_dots_* via the shared gate."""
import glob
import json
import os
import sys
import tempfile
import types

import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "editor"))
    import particle_core as C
    import particle_studio as PS
    import studio_imgui as S
    import trail_templates_ui as TTU

    schema = [{"key": f["key"], "type": f["type"],
               "min": f.get("min", 0), "max": f.get("max", 1),
               "items": list(f.get("items", []))} for f in PS.TRAIL_SCHEMA]
    assert C.templates_init(schema, tempfile.gettempdir()) == 79

    files = sorted(glob.glob(os.path.join(
        ROOT, "assets", "presets", "trails", "*", "*.json")))
    assert len(files) == 27, len(files)
    ids = []
    for p in files:
        tid = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("settings", {}).get("hideParticle") is True, tid
        assert C.templates_register(tid, data, False) is None, tid
        ids.append(tid)

    # every template x 2d/3d: merge keeps ribbons-only + viewport gate hides dots
    for tid in ids:
        for mode in ("2d", "3d"):
            new, _ch = C.templates_apply(
                tid, mode, PS.default_trails(), PS.default_trails())
            assert new.get("hideParticle") is True, (tid, mode)
            assert new.get("enabled") is True, (tid, mode)
            app = types.SimpleNamespace(trail=True)
            em = {"trails": new}
            assert S.trails_on(app, em) is True, (tid, mode)
            assert S._hide_trail_particles(em) is True, (tid, mode)

    # the apply-path force: a hostile file with false still lands true
    new = dict(PS.default_trails())
    new["hideParticle"] = False
    new2, ch2 = TTU._force_ribbons_only(new, [])
    assert new2["hideParticle"] is True and "hideParticle" in ch2
    new3, ch3 = TTU._force_ribbons_only(dict(PS.default_trails()), [])
    assert new3["hideParticle"] is True and ch3 == []
    print("TRAILS-NODOTS-OK (%d templates x 2 modes)" % len(ids))
finally:
    dpg.destroy_context()
