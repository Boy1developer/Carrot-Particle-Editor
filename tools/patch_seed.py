# Patches AdvancedParticleEmitter.json (2D + 3D runtimes) for deterministic
# seed (Phase 7.5). Run once; re-runs are a no-op.
#
#  1. F.srand/F.rrand (mulberry32) defined once per object namespace.
#     seed 0 (or missing) = legacy unseeded behavior (Math.random fallback).
#  2. Every spawn-time Math.random() -> F.rrand(). Update loops are pure
#     functions of stored per-particle state (verified: zero Math.random in
#     the update regions), so seeding spawn draws suffices for full replay.
#     Safe scoping: all 39 sites sit textually after their chunk's `var F`
#     assignment (top-level ones) or inside function bodies called later.
#  3. normalizeEmitter preserves emitter.seed through its whitelist.
#  4. MAIN UPDATE reseeds only on data-identity or seed-value change — never
#     per frame. The resetEffect branch reseeds for identical restarts.
#  5. Format doc comments bumped 1.0 -> 1.1.
#
# Anchors assert occurrence counts; modified chunks pass node --check
# (wrapped in a function since chunks may contain bare `return`).
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")

SEED_DEFS = """F.srand = F.srand || function(seed) {
  seed = seed | 0;
  if (!seed) { F._rs = null; return; }
  F._rs = { on: true, x: seed };
};
F.rrand = F.rrand || function() {
  var st = F._rs;
  if (!st || !st.on) return Math.random();
  var x = (st.x |= 0);
  x = (x + 0x6D2B79F5) | 0;
  st.x = x;
  var t = Math.imul(x ^ (x >>> 15), 1 | x);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};"""


def _indent(block, prefix="  "):
    return "\n".join(prefix + ln if ln.strip() else ln
                      for ln in block.split("\n"))


def _replace_once(text, old, new, what):
    assert text.count(old) == 1, "%s anchor x%d" % (what, text.count(old))
    return text.replace(old, new, 1)


def _walk(evts):
    for ev in evts or []:
        if ev.get("type") == "BuiltinCommonInstructions::JsCode":
            code = ev.get("inlineCode", [])
            text = "\n".join(code) if isinstance(code, list) else str(code)
            yield ev, text
        for r in _walk(ev.get("events", [])):
            yield r


def _chunks_of(doc, name):
    obj = [x for x in doc["eventsBasedObjects"] if x["name"] == name][0]
    hits = []
    for fn in obj.get("eventsFunctions", []):
        hits.extend(list(_walk(fn.get("events", []))))
    return hits


def main():
    with io.open(EXT, encoding="utf-8") as f:
        raw = f.read()
    if "F.srand = F.srand || function(seed) {" in raw:
        print("ALREADY-PATCHED")
        return
    doc = json.loads(raw)
    changed = []  # (label, text) for syntax check

    for oname, ns in (("AvancedParticleEmitter2D", "2D"),
                      ("AvancedParticleEmitter3D", "3D")):
        hits = _chunks_of(doc, oname)

        # 2) spawn-time randomness through the seeded stream. Runs FIRST so
        #    the defs inserted below (single Math.random fallback) are kept.
        #    All sites sit textually after their chunk's `var F` assignment
        #    or inside function bodies called later: F is always bound.
        total_random = 0
        for ev2, t2 in hits:
            n = t2.count("Math.random()")
            if not n:
                continue
            total_random += n
            t2 = t2.replace("Math.random()", "F.rrand()")
            ev2["inlineCode"] = t2.split("\n")
            changed.append(("%s random %d" % (ns, n), t2))
        assert total_random > 0, "%s: no Math.random found" % ns
        expected = {"2D": 15, "3D": 24}[ns]
        assert total_random == expected, \
            "%s: Math.random x%d (expected %d)" % (ns, total_random, expected)

        # 1) RNG defs after the namespace creation (once-guard block)
        hits = _chunks_of(doc, oname)  # re-read: step 2 rewrote inlineCode
        defs_hits = [(ev, t) for ev, t in hits
                     if "object.__apfx%sFns = {};" % ns in t]
        assert len(defs_hits) == 1, "%s defs chunk x%d" % (ns, len(defs_hits))
        ev, text = defs_hits[0]
        # NOTE: `var F` must precede the defs: this spot runs before the
        # chunk's own `var F = ...` line (F hoisted but undefined there).
        # Later duplicate `var F` re-declaration is harmless (same value).
        text = _replace_once(
            text,
            "object.__apfx%sFns = {};" % ns,
            "object.__apfx%sFns = {};\n  var F = object.__apfx%sFns;\n%s"
            % (ns, ns, _indent(SEED_DEFS)),
            "%s seed defs" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s defs" % ns, text))

        # 3) normalizeEmitter preserves the seed through its whitelist
        hits = _chunks_of(doc, oname)  # re-read: prior steps rewrote inlineCode
        norm_hits = [(ev, t) for ev, t in hits
                     if "blendingMode: src.blendingMode || 'Normal'," in t]
        assert len(norm_hits) == 1, "%s normalize chunk x%d" % (ns, len(norm_hits))
        ev, text = norm_hits[0]
        text = _replace_once(
            text,
            "blendingMode: src.blendingMode || 'Normal',",
            "blendingMode: src.blendingMode || 'Normal',\n"
            "      seed: (src.seed | 0),",
            "%s normalize seed" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s normalize" % ns, text))

        # 4) MAIN UPDATE: reseed on data-identity/seed change only
        hits = _chunks_of(doc, oname)  # re-read again (see above)
        upd_hits = [(ev, t) for ev, t in hits
                    if ("var F = object.__apfx%sFns;\n\nif (resetEffect) {" % ns) in t]
        assert len(upd_hits) == 1, "%s update chunk x%d" % (ns, len(upd_hits))
        ev, text = upd_hits[0]
        text = _replace_once(
            text,
            "var F = object.__apfx%sFns;\n\nif (resetEffect) {" % ns,
            "var F = object.__apfx%sFns;\n"
            "var _seedNow = (data.emitter && data.emitter.seed) | 0;\n"
            "if (F._seedData !== data || F._seedUsed !== _seedNow)"
            " { F.srand(_seedNow); F._seedUsed = _seedNow; F._seedData = data; }\n"
            "\nif (resetEffect) {" % ns,
            "%s reseed guard" % ns)
        text = _replace_once(
            text,
            "  data.time = 0;\n  object._setResetEffect(false);",
            "  data.time = 0;\n  F.srand(_seedNow);\n  object._setResetEffect(false);",
            "%s reset reseed" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s update" % ns, text))

    # 5) format doc comments 1.0 -> 1.1 (escaped quotes: raw JSON strings)
    raw2 = json.dumps(doc, ensure_ascii=False, indent=2)
    assert raw2.count('{ version:\\"1.0\\", type:\\"2d\\",') == 1, "doc2d"
    assert raw2.count('{ version:\\"1.0\\", type:\\"3d\\",') == 1, "doc3d"
    # NOTE: applied on the dumped text after chunk edits (same content)
    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        f.write(raw2.replace('{ version:\\"1.0\\", type:', '{ version:\\"1.1\\", type:'))

    for label, text in changed:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as tf:
            tf.write("function __chk(){\n" + text + "\n}")
            tmp = tf.name
        r = subprocess.run(["node", "--check", tmp],
                           capture_output=True, text=True)
        os.unlink(tmp)
        assert r.returncode == 0, label + ": " + r.stderr[-2000:]
    print("PATCHED-OK")


if __name__ == "__main__":
    sys.exit(main())
