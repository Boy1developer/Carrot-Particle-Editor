# Custom-mesh preview: uploaded GLB renders as itself, not a hollow box.
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

    tmp = tempfile.mkdtemp(prefix="carrot_mesh_")
    glb = os.path.join(tmp, "quad.glb")
    verts = [-2.0, 0.0, 0.0, 6.0, 0.0, 0.0,
             6.0, 4.0, 0.0, -2.0, 4.0, 0.0]
    idx = [0, 1, 2, 0, 2, 3]
    vbin = struct.pack("<12f", *verts) + struct.pack("<6H", *idx)
    doc = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": "Body", "mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0},
                                    "indices": 1, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4,
             "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 6,
             "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 48},
            {"buffer": 0, "byteOffset": 48, "byteLength": 12},
        ],
        "buffers": [{"byteLength": 60}],
    }
    js = json.dumps(doc).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    blob = (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(vbin))
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(vbin), 0x004E4942) + vbin)
    with open(glb, "wb") as f:
        f.write(blob)

    # 1) parse: 2 tris, centered, longest extent 2.0
    tris = mesh_cache.load_mesh_tris(glb, "Body")
    assert tris and len(tris) == 2, tris
    xs = [v[0] for t in tris for v in t]
    assert abs((max(xs) - min(xs)) - 2.0) < 1e-6
    assert abs((min(xs) + max(xs)) / 2) < 1e-6
    assert mesh_cache.load_mesh_tris(glb, "Nope") is None
    assert mesh_cache.load_mesh_tris(glb + ".missing", "") is None

    # 1b) materials: stdlib PNG decode + baseColorFactor + texture sample
    import zlib
    png_rows = [[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (255, 255, 255)]]
    raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row)
                   for row in png_rows)


    def _chunk(t, d):
        c = t + d
        return (struct.pack(">I", len(d)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xffffffff))


    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))
    w, h, flat = mesh_cache._decode_png(png)
    assert (w, h) == (2, 2), (w, h)
    assert flat[0:3] == [255, 0, 0] and flat[9:12] == [255, 255, 255], flat
    assert mesh_cache._sample((2, 2, flat), 0.667, 0.333) == (255, 255, 255)
    assert mesh_cache._sample((2, 2, flat), 0.1, 0.9) == (255, 0, 0)

    tverts = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0]
    tuvs = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    tbin = (struct.pack("<12f", *tverts) + struct.pack("<6H", *idx)
            + struct.pack("<8f", *tuvs) + png)
    tdoc = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": "Skin", "mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0,
                                                   "TEXCOORD_0": 2},
                                    "indices": 1, "material": 0,
                                    "mode": 4}]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
            "baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": 3, "mimeType": "image/png"}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4,
             "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 6,
             "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5126, "count": 4,
             "type": "VEC2"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 48},
            {"buffer": 0, "byteOffset": 48, "byteLength": 12},
            {"buffer": 0, "byteOffset": 60, "byteLength": 32},
            {"buffer": 0, "byteOffset": 92, "byteLength": len(png)},
        ],
        "buffers": [{"byteLength": 92 + len(png)}],
    }
    tjs = json.dumps(tdoc).encode()
    tjs += b" " * ((4 - len(tjs) % 4) % 4)
    tglb = os.path.join(tmp, "skin.glb")
    with open(tglb, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(tjs) + 8
                                      + len(tbin))
                + struct.pack("<II", len(tjs), 0x4E4F534A) + tjs
                + struct.pack("<II", len(tbin), 0x004E4942) + tbin)
    ttris, ttex = mesh_cache.load_mesh(tglb, "Skin")
    assert ttris and len(ttris) == 2 and len(ttex) == 2, (ttris, ttex)
    # tri1 uv-centroid (0.667,0.333) -> white texel; tri2 -> red texel
    assert ttex[0] == (255, 255, 255), ttex
    assert ttex[1] == (255, 0, 0), ttex

    # 2) integration: custom-shaped state resolves its mesh, draws polys
    S.build_ui()
    app = S.APP
    st = app.states[app.sel_state]
    old_shape, old_cm = st.get("shape"), st.get("customModel")
    st["shape"] = "custom"
    st["customModel"] = {"file": "quad.glb", "path": glb, "node": "Body",
                         "kind": "model", "nodes": ["Body"]}
    try:
        got = S.custom_mesh_tris()
        assert got and len(got) == 2, got
        calls = []
        real_poly = dpg.draw_polygon
        dpg.draw_polygon = lambda pts, **kw: calls.append(list(pts))
        try:
            ok = S.draw_custom_mesh_3d("vp_draw", app, 0.0, 0.0, 0.0,
                                      10.0, [255, 170, 0, 255], 400, 300)
        finally:
            dpg.draw_polygon = real_poly
        assert ok is True
        assert len(calls) == 2, calls
        for pts in calls:
            assert len(pts) == 3 and all(len(p) == 2 for p in pts)
        # missing file -> graceful fallback (no mesh, draw returns False)
        st["customModel"] = {"file": "gone.glb", "path": glb + ".gone",
                             "node": "", "kind": "model", "nodes": []}
        assert S.custom_mesh_tris() is None
        assert S.draw_custom_mesh_3d("vp_draw", app, 0, 0, 0, 10,
                                    [255, 0, 0, 255], 400, 300) is False
        # tint: white shows natural texels, red multiplies over them
        st["customModel"] = {"file": "skin.glb", "path": tglb,
                             "node": "Skin", "kind": "model",
                             "nodes": ["Skin"]}
        fills = []
        dpg.draw_polygon = lambda pts, **kw: fills.append(kw.get("fill"))
        try:
            assert S.draw_custom_mesh_3d("vp_draw", app, 0.0, 0.0, 0.0,
                                        10.0, [255, 255, 255, 255],
                                        400, 300) is True
        finally:
            dpg.draw_polygon = real_poly
        assert fills == [[255, 255, 255, 255], [255, 0, 0, 255]], fills
        fills.clear()
        dpg.draw_polygon = lambda pts, **kw: fills.append(kw.get("fill"))
        try:
            assert S.draw_custom_mesh_3d("vp_draw", app, 0.0, 0.0, 0.0,
                                        10.0, [255, 0, 0, 255], 400, 300) \
                is True
        finally:
            dpg.draw_polygon = real_poly
        assert fills == [[255, 0, 0, 255], [255, 0, 0, 255]], fills
    finally:
        st["shape"] = old_shape
        if old_cm is None:
            st.pop("customModel", None)
        else:
            st["customModel"] = old_cm
    print("MESH-OK")
finally:
    dpg.destroy_context()
