# -*- coding: utf-8 -*-
"""Generate language bindings from contracts/contracts.json (single source of truth).

Usage:
  python tools/generate_contracts.py          # write contracts/gen/*
  python tools/generate_contracts.py --check  # fail if committed files are stale
                                              # or if consumers drifted (CI uses this)

Outputs (deterministic, no timestamps — byte-stable):
  contracts/gen/contracts.py    Python constants
  contracts/gen/contracts.h     C++ header (included by core/particle_core.cpp)
  contracts/gen/contracts.ts    TypeScript constants (reference for preview/runtime)
  contracts/gen/schema.json     Export JSON Schema (validated by particle_studio)

Consumer wiring:
  Python + C++ import the generated files directly.
  TypeScript (preview/, carrots-runtime/) and the GDevelop extension keep
  their own copies for build reasons (rootDir/bundling); --check verifies
  their embedded literals match contracts.json instead of rewriting them.
"""
import difflib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "contracts", "contracts.json")
GEN = os.path.join(ROOT, "contracts", "gen")

HEADER = "DO NOT EDIT — generated from contracts/contracts.json by tools/generate_contracts.py"


def load():
    with io.open(SRC, encoding="utf-8") as f:
        return json.load(f)


def py_mod(c):
    L = []
    L.append("# -*- coding: utf-8 -*-")
    L.append('"""%s."""' % HEADER)
    L.append("EXPORT_VERSION = %r" % c["export_version"])
    L.append("RECORD_FIELDS = %r" % (c["record_fields"],))
    L.append("RECORD_INDEX = {name: i for i, name in enumerate(RECORD_FIELDS)}")
    L.append("SHAPE_ORDER = %r" % (c["shape_order"],))
    L.append("SHAPES_2D = %r" % (c["shapes_2d"],))
    L.append("SHAPES_3D = %r" % (c["shapes_3d"],))
    L.append("EASINGS = %r" % (c["easings"],))
    L.append("EASING_ALIASES = %r" % (c["easing_aliases"],))
    L.append("BLEND_MODES = %r" % (c["blend_modes"],))
    L.append("MORPH_LO = %r" % (c["morph_window"]["lo"],))
    L.append("MORPH_HI = %r" % (c["morph_window"]["hi"],))
    return "\n".join(L) + "\n"


def _cxx_list(items):
    return "{" + ", ".join('"%s"' % s for s in items) + "}"


def h_file(c):
    n = len(c["shape_order"])
    L = []
    L.append("// %s." % HEADER)
    L.append("#pragma once")
    L.append("")
    L.append("// Export format version (must match effect JSON \"version\").")
    L.append('constexpr const char* CARROT_EXPORT_VERSION = "%s";' % c["export_version"])
    L.append("")
    L.append("// Particle record layout: %d fields (see RECORD_FIELDS)." % len(c["record_fields"]))
    L.append("constexpr int CARROT_RECORD_FIELD_COUNT = %d;" % len(c["record_fields"]))
    L.append("")
    L.append("constexpr int CARROT_SHAPE_COUNT = %d;" % n)
    L.append("constexpr const char* CARROT_SHAPE_ORDER[CARROT_SHAPE_COUNT] = %s;"
             % _cxx_list(c["shape_order"]))
    L.append("")
    L.append("constexpr int CARROT_EASING_COUNT = %d;" % len(c["easings"]))
    L.append("constexpr const char* CARROT_EASINGS[CARROT_EASING_COUNT] = %s;"
             % _cxx_list(c["easings"]))
    L.append("")
    L.append("constexpr int CARROT_BLEND_MODE_COUNT = %d;" % len(c["blend_modes"]))
    L.append("constexpr const char* CARROT_BLEND_MODES[CARROT_BLEND_MODE_COUNT] = %s;"
             % _cxx_list(c["blend_modes"]))
    L.append("")
    L.append("// Shape cross-fade window (raw segment time).")
    L.append("constexpr double CARROT_MORPH_LO = %r;" % (c["morph_window"]["lo"],))
    L.append("constexpr double CARROT_MORPH_HI = %r;" % (c["morph_window"]["hi"],))
    return "\n".join(L) + "\n"


def _ts_list(items):
    return "[\n" + "".join('  "%s",\n' % s for s in items) + "]"


def ts_file(c):
    L = []
    L.append("// %s." % HEADER)
    L.append("// Import path (preview + carrots-runtime tsconfigs allow ../contracts):")
    L.append('//   import { SHAPE_ORDER } from "../../contracts/gen/contracts";')
    L.append('export const EXPORT_VERSION = "%s" as const;' % c["export_version"])
    L.append("export const RECORD_FIELDS = %s as const;" % _ts_list(c["record_fields"]))
    L.append("export const SHAPE_ORDER = %s as const;" % _ts_list(c["shape_order"]))
    L.append("export type ShapeName = (typeof SHAPE_ORDER)[number];")
    L.append("export const SHAPES_2D = %s as const;" % _ts_list(c["shapes_2d"]))
    L.append("export const SHAPES_3D = %s as const;" % _ts_list(c["shapes_3d"]))
    L.append("export const EASINGS = %s as const;" % _ts_list(c["easings"]))
    L.append("export type Easing = (typeof EASINGS)[number];")
    L.append("export const EASING_ALIASES: Record<string, string> = %s;"
             % json.dumps(c["easing_aliases"], indent=2))
    L.append("export const BLEND_MODES = %s as const;" % _ts_list(c["blend_modes"]))
    L.append("export type BlendMode = (typeof BLEND_MODES)[number];")
    L.append("export const MORPH_LO = %r;" % (c["morph_window"]["lo"],))
    L.append("export const MORPH_HI = %r;" % (c["morph_window"]["hi"],))
    return "\n".join(L) + "\n"


def schema_file(c):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "CarrotParticleEffect",
        "type": "object",
        "required": ["version", "type", "emitter", "states"],
        "properties": {
            "version": {"enum": [c["export_version"]]},
            "type": {"enum": ["2d", "3d"]},
            "emitter": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string"},
                    "flow": {"type": "number"},
                    "maxParticles": {"type": "number"},
                    "blendingMode": {"enum": c["blend_modes"]},
                    "seed": {"type": "number"},
                    "trails": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "source": {"type": "string"},
                            "maxPoints": {"type": "number"},
                            "lifetime": {"type": "number"},
                            "minDist": {"type": "number"},
                            "minTime": {"type": "number"},
                            "autodestruct": {"type": "boolean"},
                            "timeScale": {"type": "number"},
                            "space": {"type": "string"},
                            "fadeStop": {"type": "number"},
                            "widthStart": {"type": "number"},
                            "widthEnd": {"type": "number"},
                            "widthMult": {"type": "number"},
                            "widthCurve": {"type": "array"},
                            "smoothing": {"type": "number"},
                            "cornerVerts": {"type": "number"},
                            "capVerts": {"type": "number"},
                            "capStyle": {"type": "string"},
                            "ribbon": {"type": "string"},
                            "taper": {"type": "number"},
                            "taperHead": {"type": "boolean"},
                            "taperTail": {"type": "boolean"},
                            "wNoiseAmt": {"type": "number"},
                            "wNoiseScale": {"type": "number"},
                            "simplifyTol": {"type": "number"},
                            "colorHead": {"type": "string"},
                            "colorTail": {"type": "string"},
                            "alphaHead": {"type": "number"},
                            "alphaTail": {"type": "number"},
                            "colorStops": {"type": "array"},
                            "alphaStops": {"type": "array"},
                            "lifeColorStops": {"type": "array"},
                            "lifeAlphaStops": {"type": "array"},
                            "intensity": {"type": "number"},
                            "inheritColor": {"type": "boolean"},
                            "fadeTail": {"type": "boolean"},
                            "tailLen": {"type": "number"},
                            "texture": {"type": "string"},
                            "blend": {"type": "string"},
                            "uvMode": {"type": "string"},
                            "tileLength": {"type": "number"},
                            "tileX": {"type": "number"},
                            "tileY": {"type": "number"},
                            "offX": {"type": "number"},
                            "offY": {"type": "number"},
                            "scrollU": {"type": "number"},
                            "scrollV": {"type": "number"},
                            "flipCols": {"type": "number"},
                            "flipRows": {"type": "number"},
                            "flipFPS": {"type": "number"},
                            "trailMode": {"type": "string"},
                            "ratio": {"type": "number"},
                            "sizeAffectsWidth": {"type": "boolean"},
                            "sizeAffectsLifetime": {"type": "boolean"},
                            "dieWithParticles": {"type": "boolean"},
                            "splitRibbons": {"type": "boolean"},
                            "attachRibbons": {"type": "boolean"},
                            "genLighting": {"type": "boolean"},
                            "castShadow": {"type": "boolean"},
                            "receiveShadow": {"type": "boolean"},
                            "sortLayer": {"type": "string"},
                            "sortOrder": {"type": "number"},
                            "softFade": {"type": "number"},
                            "gravity": {"type": "number"},
                            "drag": {"type": "number"},
                            "noise": {"type": "number"},
                            "hideParticle": {"type": "boolean"},
                            "lifetimeJitter": {"type": "number"},
                            "minScreenWidth": {"type": "number"},
                            "edgeSoftness": {"type": "number"},
                            "coreColor": {"type": "string"},
                            "coreWidth": {"type": "number"},
                            "edgeColor": {"type": "string"},
                            "glowWidth": {"type": "number"},
                            "glowAlpha": {"type": "number"},
                            "flickerAmt": {"type": "number"},
                            "flickerHz": {"type": "number"},
                        },
                    },
                    "fields": {
                        "type": "object",
                        "properties": {
                            "turbulence": {
                                "type": "object",
                                "properties": {
                                    "amount": {"type": "number"},
                                    "scale": {"type": "number"},
                                    "speed": {"type": "number"},
                                },
                            },
                            "vortex": {
                                "type": "object",
                                "properties": {"strength": {"type": "number"}},
                            },
                            "attractor": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"},
                                    "y": {"type": "number"},
                                    "z": {"type": "number"},
                                    "strength": {"type": "number"},
                                    "radius": {"type": "number"},
                                },
                            },
                            "collision": {
                                "type": "object",
                                "properties": {
                                    "bounce": {"type": "number"},
                                    "friction": {"type": "number"},
                                },
                            },
                        },
                    },
                },
            },
            "states": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "required": ["duration", "shape", "easing"],
                    "properties": {
                        "duration": {"type": "number"},
                        "shape": {"type": "string"},
                        "easing": {"enum": c["easings"]},
                        "appearance": {"type": "object"},
                        "movement": {"type": "object"},
                    },
                },
            },
            "models": {"type": "object"},
        },
    }
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def render_all(c):
    return {
        "contracts.py": py_mod(c),
        "contracts.h": h_file(c),
        "contracts.ts": ts_file(c),
        "schema.json": schema_file(c),
    }


def write_all(files):
    os.makedirs(GEN, exist_ok=True)
    for name, text in files.items():
        with io.open(os.path.join(GEN, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


# ---- drift checks against consumers that keep their own copies ----

def _read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _py_str_list(src, var):
    m = re.search(var + r"\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "list %s not found" % var
    return re.findall(r'"([^"]+)"', m.group(1))


def check_consumers(c):
    errs = []
    # 1) C++ must include the generated header (single source, not a copy)
    cpp = _read(os.path.join("core", "particle_core.cpp"))
    if "contracts/gen/contracts.h" not in cpp and "CARROT_SHAPE_ORDER" not in cpp:
        errs.append("core/particle_core.cpp does not use contracts/gen/contracts.h")
    # 2) carrots-runtime keeps its own literals (rootDir) — must match
    ts = _read(os.path.join("carrots-runtime", "src", "carrot-effect.ts"))
    if _py_str_list(ts, "SHAPE_ORDER") != c["shape_order"]:
        errs.append("carrots-runtime SHAPE_ORDER drifted from contracts.json")
    if _py_str_list(ts, "EASINGS") != c["easings"]:
        errs.append("carrots-runtime EASINGS drifted from contracts.json")
    m = re.search(r'CARROT_EFFECT_VERSION\s*=\s*"([^"]+)"', ts)
    if not m or m.group(1) != c["export_version"]:
        errs.append("carrots-runtime CARROT_EFFECT_VERSION drifted")
    # 3) extension keeps its own literals (bundled JSON) — choice lists must match
    ext = _read("AdvancedParticleEmitter.json")
    for want in [c["blend_modes"], ["JSON"] + c["blend_modes"]]:
        # supplementaryInformation stores the list as an escaped JSON string
        enc = json.dumps(want, separators=(",", ":")).replace('"', '\\"')
        if enc not in ext:
            errs.append("extension BlendingMode choices drifted: %s" % (want,))
    for em in ("pixiBlendMode", "createMesh", "SubtractiveBlending"):
        if em not in ext:
            errs.append("extension missing blend runtime block: %s" % em)
    for ez in c["easings"]:
        if ez not in ext:
            errs.append("extension missing easing value: %s" % ez)
    for sh in c["shape_order"]:
        if sh not in ext:
            errs.append("extension missing shape name: %s" % sh)
    # 4) sample effect must validate against the schema
    try:
        eff = json.loads(_read("sample_effect.json"))
    except Exception as e:  # noqa: BLE001
        errs.append("sample_effect.json invalid: %s" % e)
    else:
        sys.path.insert(0, os.path.join(ROOT, "editor"))
        import particle_studio as PS
        errs.extend("sample_effect.json: " + e
                    for e in PS.validate_against_schema(eff))
    return errs


def main():
    check = "--check" in sys.argv[1:]
    c = load()
    files = render_all(c)
    if not check:
        write_all(files)
        print("generated %d files in contracts/gen/" % len(files))
        return
    errs = []
    for name, text in files.items():
        p = os.path.join(GEN, name)
        try:
            with io.open(p, encoding="utf-8") as f:
                cur = f.read()
        except OSError:
            errs.append("missing generated file: contracts/gen/%s" % name)
            continue
        if cur != text:
            diff = "".join(difflib.unified_diff(
                cur.splitlines(True), text.splitlines(True),
                "committed contracts/gen/" + name, "regenerated", n=3))
            errs.append("stale generated file: contracts/gen/%s\n%s" % (name, diff))
    errs.extend(check_consumers(c))
    if errs:
        print("CONTRACT-CHECK FAILED:")
        for e in errs:
            try:
                print("-", e)
            except UnicodeEncodeError:
                print("-", str(e).encode("ascii", "backslashreplace").decode("ascii"))
        sys.exit(1)
    print("CONTRACT-CHECK OK")


if __name__ == "__main__":
    main()
