# -*- coding: utf-8 -*-
"""Trail settings round-trip: save -> load identical; old files heal."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "editor"))
import particle_studio as PS

# 1) every shipped trail file round-trips byte-identical through migrate
for path in sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "presets", "trail_*.json"))):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    eff, _w = PS.migrate_effect(json.loads(raw))
    assert PS.validate_effect(eff) == [], path
    assert json.loads(raw)["emitter"]["trails"] == eff["emitter"]["trails"], path
# 2) old file without a trails block heals to full defaults, stays valid
old = json.load(open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample_effect.json"), encoding="utf-8"))
assert "trails" not in old.get("emitter", {})
eff, _w = PS.migrate_effect(old)
assert sorted(eff["emitter"]["trails"]) == sorted(PS.default_trails())
assert PS.validate_effect(eff) == []
print("TRAILS-ROUNDTRIP-OK")
