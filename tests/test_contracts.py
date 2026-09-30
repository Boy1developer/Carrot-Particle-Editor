# Contract tests: generated bindings match the single source (contracts.json),
# the schema accepts real exports, rejects broken ones, and migration heals old files.
import json
import os
import subprocess
import sys

import bootstrap  # noqa: F401  (repo root + editor/ on sys.path)

import particle_studio as PS
from contracts.gen import contracts as GEN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "contracts", "contracts.json"), encoding="utf-8") as f:
    C = json.load(f)

# 1) generated Python bindings == source
assert GEN.EXPORT_VERSION == C["export_version"] == PS.VERSION
assert GEN.SHAPE_ORDER == C["shape_order"] == PS.SHAPE_ORDER
assert GEN.SHAPES_2D == C["shapes_2d"] == PS.SHAPES_2D
assert GEN.SHAPES_3D == C["shapes_3d"] == PS.SHAPES_3D
assert GEN.EASINGS == C["easings"] == PS.EASINGS
assert GEN.EASING_ALIASES == C["easing_aliases"] == PS.EASING_ALIASES
assert GEN.BLEND_MODES == C["blend_modes"] == PS.BLEND_MODES
assert GEN.RECORD_FIELDS == C["record_fields"] and len(GEN.RECORD_FIELDS) == 22
assert GEN.RECORD_INDEX["speedRatio"] == 21 and GEN.RECORD_INDEX["x"] == 0
assert (GEN.MORPH_LO, GEN.MORPH_HI) == (0.25, 0.75)
print("bindings match source: OK")

# 2) C++ module shape order == source (built from the generated header)
import particle_core as core
assert list(core.SHAPE_ORDER) == C["shape_order"], core.SHAPE_ORDER
print("c++ shape order: OK")

# 3) generator is byte-stable (no drift between runs)
r = subprocess.run([sys.executable, "tools/generate_contracts.py", "--check"],
                   capture_output=True, text=True, cwd=ROOT)
assert r.returncode == 0, r.stdout + r.stderr
print("generate --check: OK")

# 4) schema accepts the sample export and a live-built effect
with open(os.path.join(ROOT, "sample_effect.json"), encoding="utf-8") as f:
    sample = json.load(f)
assert PS.validate_against_schema(sample) == [], PS.validate_against_schema(sample)
import studio_imgui as S
app = S.App()
assert PS.validate_effect(app.current_effect()) == []
print("schema accepts real effects: OK")

# 5) schema rejects broken effects
bad = {"version": "1.0", "type": "sideways", "emitter": {}, "states": []}
errs = PS.validate_against_schema(bad)
assert any("type" in e for e in errs) and any("states" in e for e in errs), errs
bad2 = json.loads(json.dumps(sample))
bad2["states"][0]["easing"] = "easeIn"
assert any("easing" in e for e in PS.validate_against_schema(bad2))
bad3 = json.loads(json.dumps(sample))
bad3["emitter"]["blendingMode"] = "Screen"
assert any("blendingMode" in e for e in PS.validate_against_schema(bad3)), \
    PS.validate_against_schema(bad3)
print("schema rejects broken effects: OK")

# 6) migration heals old files; old files render exactly as before
legacy = {"type": "2d", "emitter": {},
          "states": [{"duration": 0.5, "shape": "Circle", "easing": "easeIn"},
                     {"duration": 0.5, "shape": "circle", "easing": "linear"}]}
mig, warns = PS.migrate_effect(legacy)
assert mig["version"] == "1.0" and mig["states"][0]["easing"] == "ease-in"
assert mig["states"][0]["shape"] == "circle" and mig["emitter"]["blendingMode"] == "Normal"
assert warns, warns
assert PS.validate_against_schema(mig) == []
# legacy input untouched (deep copy)
assert "version" not in legacy and legacy["states"][0]["easing"] == "easeIn"
try:
    PS.migrate_effect({"version": "9.9"})
    raise SystemExit("FAIL: newer version should raise")
except ValueError:
    pass
try:
    PS.migrate_effect([1, 2])
    raise SystemExit("FAIL: non-object should raise")
except ValueError:
    pass
print("migration: OK")
print("CONTRACTS-OK")
