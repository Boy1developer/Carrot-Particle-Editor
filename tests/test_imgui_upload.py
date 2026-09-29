# Upload chain: dialog payload -> customModel -> form text + status.
# Also covers Wavefront OBJ parsing (v/f, fans, negative indices).
import json
import os
import struct
import tempfile

import bootstrap  # tests/ sys.path setup (repo root + editor/)
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import mesh_cache
    import studio_imgui as S

    # 1) OBJ parse
    tmp = tempfile.mkdtemp(prefix="carrot_up_")
    obj = os.path.join(tmp, "box.obj")
    with open(obj, "w") as f:
        f.write("# cube-ish\nv 0 0 0\nv 2 0 0\nv 2 2 0\nv 0 2 0\n"
                "v 0 0 2\njunk line here\n"
                "f 1 2 3 4\n"          # quad -> 2 tris (fan)
                "f -5 -4 -3\n")        # negative indices -> 1 tri
    tris = mesh_cache.load_mesh_tris(obj, "")
    assert tris and len(tris) == 3, tris
    xs = [v[0] for t in tris for v in t]
    assert abs((max(xs) - min(xs)) - 2.0) < 1e-6
    assert mesh_cache.load_mesh_tris(obj + ".missing", "") is None

    # 2) upload chain with a realistic DPG file-dialog payload
    S.build_ui()
    S.APP.sync_all()
    app = S.APP
    app.sel_state = 0
    st = app.states[0]
    st["shape"] = "custom"
    st.pop("customModel", None)
    st.pop("modelRefs", None)
    app.sync_state_form()
    assert dpg.get_value("custom_file_text") == "no file"

    S.model_chosen("dlg_model", {"file_path_name": obj,
                                 "file_name": "box.obj",
                                 "current_path": tmp,
                                 "selections": {"box.obj": obj}})
    cm = st.get("customModel")
    assert cm and cm.get("file") == "box.obj", cm
    assert cm.get("path") == obj, cm
    assert st.get("modelRefs") == ["box"], st.get("modelRefs")
    assert dpg.get_value("custom_file_text") == "box.obj"
    assert "box.obj" in dpg.get_value("status_text"), \
        dpg.get_value("status_text")
    # mesh resolves for the viewport
    assert S.custom_mesh_tris() is not None

    # 3) empty payload: no crash, no state change, visible status
    before = dict(st.get("customModel"))
    S.model_chosen("dlg_model", {})
    assert st.get("customModel") == before
    assert dpg.get_value("status_text") == "No file selected"

    # 4) dialog_pick accepts every known payload shape
    P = S.dialog_pick
    assert P({"selections": {"a.glb": "/x/a.glb"}}) == "/x/a.glb"
    assert P({"selections": ["/y/b.glb"]}) == "/y/b.glb"
    assert P({"file_path_name": "/z/c.glb"}) == "/z/c.glb"
    assert P({"file_path": "/z/c.glb"}) == "/z/c.glb"
    assert P({"file_name": "d.glb",
              "current_path": "/w"}) == os.path.join("/w", "d.glb")
    assert P({}) == ""
    assert P(None) == ""
    assert P("junk") == ""
    print("UPLOAD-OK")
finally:
    dpg.destroy_context()
