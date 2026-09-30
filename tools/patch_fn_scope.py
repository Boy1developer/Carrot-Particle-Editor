# One-off repair (Phase 7.5/7.3 follow-up): the seed/field helper defs were
# inserted right after `object.__apfx{2D,3D}Fns = {};` but BEFORE the chunk's
# `var F = ...` assignment, so bare `F.xxx = ...` definition lines threw
# TypeError on the first frame (F hoisted but undefined) — crashing the
# extension on add. Fix: bind `var F` immediately, before the defs.
# Idempotent; modified chunks pass node --check (function-wrapped).
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")


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
        doc = json.load(f)
    changed = []
    for oname, ns in (("AvancedParticleEmitter2D", "2D"),
                      ("AvancedParticleEmitter3D", "3D")):
        anchor = ("object.__apfx%sFns = {};\n    F.fieldsActive = F.fieldsActive || function(Flds) {"
                  % ns)
        hits = [(ev, t) for ev, t in _chunks_of(doc, oname) if anchor in t]
        if not hits:
            continue  # already repaired (or fresh tree: patch scripts handle it)
        assert len(hits) == 1, "%s repair anchor x%d" % (ns, len(hits))
        ev, text = hits[0]
        text = text.replace(
            anchor,
            "object.__apfx%sFns = {};\n  var F = object.__apfx%sFns;\n"
            "    F.fieldsActive = F.fieldsActive || function(Flds) {" % (ns, ns), 1)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s var F" % ns, text))
    if not changed:
        print("ALREADY-FIXED")
        return
    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
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
