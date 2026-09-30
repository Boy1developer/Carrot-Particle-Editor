# Blend-mode Python side: round-trip every contract mode through export,
# migration, validation and schema; sample layers file validates.
import copy
import json
import os

import bootstrap  # noqa: F401

import particle_studio as PS
import studio_imgui as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1) all contract modes survive a JSON round-trip + migration + validation
assert PS.BLEND_MODES == ["Normal", "Additive", "Subtractive", "Multiply",
                          "Screen", "Lighten", "Overlay"], PS.BLEND_MODES
app = S.App()
for mode in PS.BLEND_MODES:
    app.em["blendingMode"] = mode
    eff = app.current_effect()
    assert eff["emitter"]["blendingMode"] == mode, mode
    wire = json.loads(json.dumps(eff))
    mig, warns = PS.migrate_effect(wire)
    assert not warns, (mode, warns)
    assert PS.validate_effect(mig) == [], (mode, PS.validate_effect(mig))
    assert PS.validate_against_schema(mig) == [], mode
print("round-trip all modes: OK")

# 2) unknown mode: migration preserves (lossless), schema flags it
app.em["blendingMode"] = "Screen"
eff = app.current_effect()
eff["emitter"]["blendingMode"] = "Bogus"
assert PS.validate_against_schema(eff), "schema should flag Bogus"
mig, _ = PS.migrate_effect(eff)
assert mig["emitter"]["blendingMode"] == "Bogus"  # lossless; repair happens at read_emitter
print("schema flags unknown mode: OK")

# 3) DPG read_emitter sanitizes garbage to Normal (never exports invalid)
app.em["blendingMode"] = "Bogus"
eff = app.current_effect()
assert eff["emitter"]["blendingMode"] == "Normal", eff["emitter"]
print("read_emitter sanitizes: OK")

# 4) sample layers: 3 effects, distinct modes, all validate
with open(os.path.join(ROOT, "sample_blend_layers.json"), encoding="utf-8") as f:
    layers = json.load(f)
assert isinstance(layers, list) and len(layers) == 3, len(layers)
modes = [e["emitter"]["blendingMode"] for e in layers]
assert modes == ["Additive", "Normal", "Screen"], modes
for e in layers:
    assert PS.validate_effect(e) == [], PS.validate_effect(e)
    assert PS.validate_against_schema(e) == [], PS.validate_against_schema(e)
print("sample_blend_layers: OK")
print("BLEND-PY-OK")
