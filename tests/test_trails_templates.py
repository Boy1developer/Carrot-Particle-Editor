# -*- coding: utf-8 -*-
"""Trail templates registry (C++): load all 27, search, apply, validation."""
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "editor"))
import particle_core as C
import particle_studio as PS

schema = [{"key": f["key"], "type": f["type"],
           "min": f.get("min", 0), "max": f.get("max", 1),
           "items": list(f.get("items", []))} for f in PS.TRAIL_SCHEMA]
assert C.templates_init(schema, tempfile.gettempdir()) == 66

# 1) all builtin templates load with zero warnings
files = sorted(glob.glob(os.path.join(
    ROOT, "assets", "presets", "trails", "*", "*.json")))
assert len(files) == 27, len(files)
for p in files:
    tid = os.path.splitext(os.path.basename(p))[0]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    w = C.templates_register(tid, data, False)
    assert w is None, (tid, w)

# 2) category counts: 5/6/5/6/5
expect = {"combat": 5, "magic": 6, "movement": 5, "nature": 6,
          "stylized": 5}
for cat, n in expect.items():
    got = C.templates_list(cat, "", "2d", "name", False)
    assert len(got) == n, (cat, got)
assert len(C.templates_list("", "", "", "name", False)) == 27

# 3) search: name + tag
assert "sword_slash" in C.templates_list("combat", "sword", "2d",
                                         "name", False)
assert "wand_sparkle" in C.templates_list("", "sparkle", "2d",
                                          "name", False)
assert "fire_trail" in C.templates_list("", "fire", "2d", "name", False)

# 4) apply: empty template -> no changes; partial -> exact changed ids
C.templates_register("t_empty", {"settings": {}}, False)
nd, ch = C.templates_apply("t_empty", "2d", PS.default_trails(),
                           PS.default_trails())
assert ch == [], ch
assert sorted(nd) == sorted(PS.default_trails()), "merge must be complete"
C.templates_register("t_two", {"settings": {"lifetime": 0.25,
                                            "maxPoints": 99}}, False)
nd, ch = C.templates_apply("t_two", "2d", PS.default_trails(),
                           PS.default_trails())
assert sorted(ch) == ["lifetime", "maxPoints"], ch
assert nd["lifetime"] == 0.25 and nd["maxPoints"] == 99

# 5) validation: bad values warn + drop, unknown keys dropped silently
w = C.templates_register("t_bad", {"settings": {"lifetime": "x",
                                                "space": "bogus",
                                                "zzz_unknown": 1}}, False)
assert w and "lifetime" in w and "space" in w, w
nd, _ch = C.templates_apply("t_bad", "2d", PS.default_trails(),
                            PS.default_trails())
assert nd["lifetime"] == PS.default_trails()["lifetime"]
assert nd["space"] == PS.default_trails()["space"]

# 6) thumbnails + procedural textures sized correctly
w, h, buf = C.templates_thumbnail("sword_slash", 96, 48)
assert (w, h) == (96, 48) and len(buf) == 96 * 48 * 4
w, h, buf = C.templates_texture("flame", 64, 64)
assert (w, h) == (64, 64) and len(buf) == 64 * 64 * 4
w2, h2, buf2 = C.templates_texture("flame", 64, 64)
assert bytes(buf) == bytes(buf2), "texture cache must be deterministic"

# 7) user preset save/delete roundtrip (isolated temp dir)
with tempfile.TemporaryDirectory() as td:
    C.templates_init(schema, td)
    for p in files:  # re-register after init cleared the registry
        tid = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            C.templates_register(tid, json.load(f), False)
    cur = PS.default_trails()
    cur["lifetime"] = 1.23
    path = C.presets_save("my_test", cur, {"name": "My Test"})
    assert os.path.isfile(path), path
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["settings"]["lifetime"] == 1.23
    C.templates_register("my_test", saved, True)
    assert "my_test" in C.templates_list("user", "", "2d", "name", False)
    C.presets_delete("my_test")
    assert not os.path.isfile(path)
    assert "my_test" not in C.templates_list("user", "", "2d",
                                             "name", False)

print("TRAILS-TEMPLATES-OK")
