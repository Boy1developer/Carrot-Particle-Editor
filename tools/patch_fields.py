# Patches AdvancedParticleEmitter.json (2D + 3D runtimes) for force fields
# (Phase 7.3, format 1.1). Run once; re-runs are a no-op.
#
#  1. F.fieldsActive / F.fieldAccel / F.fieldCollision pure helpers
#     (mulberry-style defensive reads; testable headless, mirrors
#     particle_studio.field_accel exactly).
#  2. normalizeEmitter passes emitter.fields through its whitelist.
#  3. Update loops fold field acceleration into velocity (gated per frame by
#     F.fieldsActive) and enforce the collision plane. 2D uses the gravity
#     accumulator (velocities are rebuilt from dir*speed each frame, like the
#     Python sim); 3D velocity is stateful (direct response, like preview).
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

FIELD_DEFS = """F.fieldsActive = F.fieldsActive || function(Flds) {
  if (!Flds || typeof Flds !== "object") return false;
  var t = Flds.turbulence || {}, v = Flds.vortex || {},
      a = Flds.attractor || {}, c = Flds.collision || {};
  return (+(t.amount || 0)) !== 0 || (+(v.strength || 0)) !== 0 ||
         (+(a.strength || 0)) !== 0 ||
         (c.planeY !== null && c.planeY !== undefined && isFinite(+c.planeY));
};
F.fieldAccel = F.fieldAccel || function(x, y, z, age, Flds, ex, ey, ez, flat) {
  var ax = 0, ay = 0, az = 0;
  var Fd = Flds || {};
  var tb = Fd.turbulence || {};
  var tam = +(tb.amount || 0);
  if (tam !== 0) {
    var tsc = +(tb.scale || 0), tsp = +(tb.speed || 0);
    ax += tam * Math.sin(y * tsc + age * tsp);
    ay += tam * Math.sin(z * tsc * 1.3 + age * tsp * 1.1);
    az += tam * Math.sin(x * tsc * 0.7 + age * tsp * 0.9);
  }
  var vst = +(((Fd.vortex) || {}).strength || 0);
  if (vst !== 0) {
    if (flat) {
      var dx2 = x - ex, dy2 = y - ey;
      var r2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
      if (r2 > 1e-6) { var s2 = vst / Math.max(r2, 1.0); ax += -dy2 * s2; ay += dx2 * s2; }
    } else {
      var dx3 = x - ex, dz3 = z - ez;
      var r3 = Math.sqrt(dx3 * dx3 + dz3 * dz3);
      if (r3 > 1e-6) { var s3 = vst / Math.max(r3, 1.0); ax += -dz3 * s3; az += dx3 * s3; }
    }
  }
  var at = Fd.attractor || {};
  var ast = +(at.strength || 0);
  var ard = +(at.radius || 0);
  if (ast !== 0 && ard > 0) {
    var ddx = x - (+(at.x || 0)), ddy = y - (+(at.y || 0)), ddz = z - (+(at.z || 0));
    var rr = Math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
    if (rr < ard && rr > 1e-6) {
      var kk = ast * (1 - rr / ard) / rr;
      ax -= ddx * kk; ay -= ddy * kk; az -= ddz * kk;
    }
  }
  return [ax, ay, az];
};
F.fieldCollision = F.fieldCollision || function(Flds) {
  var c = (Flds || {}).collision || {};
  var py = c.planeY;
  if (py === null || py === undefined || !isFinite(+py)) return null;
  return { planeY: +py, bounce: +(c.bounce || 0), friction: +(c.friction || 0) };
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
    if "F.fieldAccel = F.fieldAccel || function(" in raw:
        print("ALREADY-PATCHED")
        return
    doc = json.loads(raw)
    changed = []

    for oname, ns, flat in (("AvancedParticleEmitter2D", "2D", True),
                            ("AvancedParticleEmitter3D", "3D", False)):
        hits = _chunks_of(doc, oname)

        # 1) pure helpers next to the RNG defs
        defs_hits = [(ev, t) for ev, t in hits
                     if "F.srand = F.srand || function(seed) {" in t]
        assert len(defs_hits) == 1, "%s defs chunk x%d" % (ns, len(defs_hits))
        ev, text = defs_hits[0]
        text = _replace_once(
            text,
            "F.srand = F.srand || function(seed) {",
            _indent(FIELD_DEFS) + "\n  F.srand = F.srand || function(seed) {",
            "%s field defs" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s defs" % ns, text))

        # 2) normalizeEmitter passes fields through (re-read: step 1 rewrote)
        hits = _chunks_of(doc, oname)
        norm_hits = [(ev, t) for ev, t in hits
                     if "      seed: (src.seed | 0)," in t]
        assert len(norm_hits) == 1, "%s normalize chunk x%d" % (ns, len(norm_hits))
        ev, text = norm_hits[0]
        text = _replace_once(
            text,
            "      seed: (src.seed | 0),",
            "      seed: (src.seed | 0),\n"
            "      fields: (src.fields && typeof src.fields === \"object\")"
            " ? src.fields : null,",
            "%s normalize fields" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s normalize" % ns, text))

        # 3) update loop: gate per frame, accel into velocity, plane collide
        hits = _chunks_of(doc, oname)
        if flat:
            loop_old = ("  var gravity = emitter.gravity || { x: 0, y: 0 };\n"
                        "  p.gvx = (p.gvx || 0) + gravity.x * dt;\n"
                        "  p.gvy = (p.gvy || 0) + gravity.y * dt;")
            loop_new = (loop_old +
                        "\n  if (_fOn) { var _fa = F.fieldAccel(p.x, p.y, 0, p.age,"
                        " emitter.fields, cx, cy, 0, true);"
                        " p.gvx += _fa[0] * dt; p.gvy += _fa[1] * dt; }")
            pos_old = ("  p.x += velX * dt; p.y += velY * dt;\n"
                       "  // Keep p.vx/p.vy in sync for any external readers / alignToVelocity below\n"
                       "  p.vx = velX; p.vy = velY;")
            pos_new = (pos_old +
                       "\n  if (_col && p.y < _col.planeY) { p.y = _col.planeY;"
                       " p.gvx += p.vx * -_col.friction;"
                       " p.gvy += -p.vy * (1 + _col.bounce); }")
            gate_old = ("for (var i = data.particles.length - 1; i >= 0; i--) {\n"
                        "  var p = data.particles[i];\n"
                        "  p.age += dt; p.segAge += dt;")
            gate_new = ("var _fOn = F.fieldsActive(data.emitter.fields);\n"
                        "var _col = _fOn ? F.fieldCollision(data.emitter.fields) : null;\n"
                        + gate_old)
        else:
            loop_old = ("    var gravity = emitter.gravity || {x:0,y:0,z:0};\n"
                        "    p.vx += gravity.x * dt; p.vy += gravity.y * dt; p.vz += gravity.z * dt;\n"
                        "    p.x  += p.vx * dt;      p.y  += p.vy * dt;      p.z  += p.vz * dt;")
            loop_new = ("    var gravity = emitter.gravity || {x:0,y:0,z:0};\n"
                        "    p.vx += gravity.x * dt; p.vy += gravity.y * dt; p.vz += gravity.z * dt;\n"
                        "    if (_fOn) { var _fa3 = F.fieldAccel(p.x, p.y, p.z, p.age,"
                        " emitter.fields, cx, cy, cz, false);"
                        " p.vx += _fa3[0] * dt; p.vy += _fa3[1] * dt; p.vz += _fa3[2] * dt; }\n"
                        "    p.x  += p.vx * dt;      p.y  += p.vy * dt;      p.z  += p.vz * dt;\n"
                        "    if (_col3 && p.y < _col3.planeY) { p.y = _col3.planeY;"
                        " p.vx *= (1 - _col3.friction); p.vy = -p.vy * _col3.bounce;"
                        " p.vz *= (1 - _col3.friction); }")
            gate_old = ("for (var i = data.particles.length - 1; i >= 0; i--) {\n"
                        "    var p = data.particles[i];")
            gate_new = ("var _fOn = F.fieldsActive(data.emitter.fields);\n"
                        "var _col3 = _fOn ? F.fieldCollision(data.emitter.fields) : null;\n"
                        + gate_old)
            pos_old = pos_new = None
        upd_hits = [(ev, t) for ev, t in hits if loop_old in t]
        assert len(upd_hits) == 1, "%s update chunk x%d" % (ns, len(upd_hits))
        ev, text = upd_hits[0]
        text = _replace_once(text, loop_old, loop_new, "%s field accel" % ns)
        if pos_old is not None:
            text = _replace_once(text, pos_old, pos_new, "%s collide" % ns)
        text = _replace_once(text, gate_old, gate_new, "%s gate" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s update" % ns, text))

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
