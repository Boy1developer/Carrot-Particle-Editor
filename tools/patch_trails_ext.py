# Patches AdvancedParticleEmitter.json (2D + 3D runtimes) for trail ribbons
# (format 1.1, extension 0.2.0). Run once; re-runs are a no-op per object.
#
#  1. F.trail* pure helpers (norm/bake/store/width/color/stride + 2D quads
#     + 3D strips), wrapped in // <carrot-trails-helpers> markers so the
#     headless tests can extract the SHIPPED block (mirrors
#     preview/trails.ts, itself parity-tested against particle_studio).
#  2. normalizeEmitter passes emitter.trails through.
#  3. Lazy trail build next to the tracks build + per-frame vars.
#  4. Per-particle history push + dot hiding in both main loops.
#  5. 2D ribbon Graphics overlay + 3D pooled ribbon strips after the loops.
#  6. Ribbon-pool disposal in 3D onDestroy.
#  7. Extension version 0.1.2 -> 0.2.0.
#
# Anchors assert occurrence counts; modified chunks pass node --check
# (wrapped in a function since chunks contain bare `return`).
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")

MARK_A = "// <carrot-trails-helpers>"
MARK_B = "// </carrot-trails-helpers>"
MARK_3A = "// <carrot-trails-3d>"
MARK_3B = "// </carrot-trails-3d>"

TRAIL_CORE_JS = r"""// <carrot-trails-helpers>
F.trailNorm = F.trailNorm || function(raw) {
  var d = (raw && typeof raw === "object") ? raw : {};
  var en = !!d.enabled;
  var mp = Math.floor(+d.maxPoints || 32);
  if (!isFinite(mp)) mp = 32;
  if (!en || mp <= 1) return null;
  var src = String(d.source != null ? d.source : "particles");
  var em = String(d.emitMode != null ? d.emitMode : "time");
  function num(v, fb) { var n = +((v === undefined || v === null) ? fb : v); return isFinite(n) ? n : fb; }
  return {
    enabled: en,
    source: src === "emitter" ? "emitter" : "particles",
    maxPoints: mp,
    lifetime: num(d.lifetime, 1.0),
    minDist: num(d.minDist, 4.0),
    minTime: num(d.minTime, 0.016),
    emitMode: em === "distance" ? "distance" : "time",
    sectionLength: num(d.sectionLength, 8.0),
    hideParticle: d.hideParticle === undefined ? true : !!d.hideParticle,
    lifetimeJitter: num(d.lifetimeJitter, 0),
    widthStart: num(d.widthStart, 8.0),
    widthEnd: num(d.widthEnd, 1.0),
    widthMult: num(d.widthMult, 1.0),
    widthCurve: Array.isArray(d.widthCurve) ? d.widthCurve : [[0, 1], [1, 1]],
    taperHead: !!d.taperHead,
    taperTail: d.taperTail === undefined ? true : !!d.taperTail,
    minScreenWidth: num(d.minScreenWidth, 2.5),
    edgeColor: String(d.edgeColor != null ? d.edgeColor : "#ffffff"),
    coreColor: String(d.coreColor != null ? d.coreColor : ""),
    coreWidth: num(d.coreWidth, 0.35),
    glowWidth: num(d.glowWidth, 0),
    glowAlpha: num(d.glowAlpha, 0),
    flickerAmt: num(d.flickerAmt, 0),
    flickerHz: num(d.flickerHz, 8.0),
    intensity: num(d.intensity, 1.0),
    colorStops: Array.isArray(d.colorStops) ? d.colorStops : [[0, "#ffffff"], [1, "#ffffff"]],
    alphaStops: Array.isArray(d.alphaStops) ? d.alphaStops : [[0, 255], [1, 0]]
  };
};
F.trailHex = F.trailHex || function(s) {
  var h = String(s != null ? s : "#ffffff");
  if (h.charAt(0) === "#") h = h.slice(1);
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  var n = parseInt(h.slice(0, 6), 16);
  if (!isFinite(n)) return [255, 255, 255];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
F.trailPyRound = F.trailPyRound || function(x) {
  var f = Math.floor(x), d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return (f % 2 === 0) ? f : f + 1;
};
F.trailEvalKeys = F.trailEvalKeys || function(keys, t, def) {
  if (def === undefined) def = 1.0;
  var pts = [], i, k;
  try {
    for (i = 0; i < (keys || []).length; i++) {
      k = keys[i];
      if (!k || k.length < 2) continue;
      pts.push([+k[0], +k[1], k.length > 2 ? String(k[2]).toLowerCase() : "smooth"]);
    }
  } catch (e) { return def; }
  for (i = 0; i < pts.length; i++) {
    if (!isFinite(pts[i][0]) || !isFinite(pts[i][1])) return def;
  }
  pts.sort(function(a, b) { return a[0] - b[0]; });
  if (!pts.length) return def;
  if (t <= pts[0][0]) return pts[0][1];
  if (t >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  for (var j = 0; j < pts.length - 1; j++) {
    var x0 = pts[j][0], y0 = pts[j][1], m = pts[j][2];
    var x1 = pts[j + 1][0], y1 = pts[j + 1][1];
    if (x0 <= t && t <= x1) {
      var u = x1 <= x0 ? 0 : (t - x0) / (x1 - x0);
      if (m === "constant") return y0;
      if (m === "linear") return y0 + (y1 - y0) * u;
      var s = u * u * (3 - 2 * u);
      return y0 + (y1 - y0) * s;
    }
  }
  return pts[pts.length - 1][1];
};
F.trailBakeCurve = F.trailBakeCurve || function(keys, n) {
  var m = Math.max(2, Math.floor(n || 64)), out = [];
  for (var i = 0; i < m; i++) out.push(F.trailEvalKeys(keys, i / (m - 1)));
  return out;
};
F.trailBakeGrad = F.trailBakeGrad || function(colorStops, alphaStops, n) {
  var m = Math.max(2, Math.floor(n || 256));
  var cs = [], aa = [], i;
  try {
    var c0 = colorStops || [], a0 = alphaStops || [];
    for (i = 0; i < c0.length; i++) {
      if (c0[i] && c0[i].length >= 2) cs.push([+c0[i][0], String(c0[i][1])]);
    }
    for (i = 0; i < a0.length; i++) {
      if (a0[i] && a0[i].length >= 2) aa.push([+a0[i][0], +a0[i][1]]);
    }
    for (i = 0; i < cs.length; i++) { if (!isFinite(cs[i][0])) throw 0; }
    for (i = 0; i < aa.length; i++) { if (!isFinite(aa[i][0]) || !isFinite(aa[i][1])) throw 0; }
  } catch (e) { cs = []; aa = []; }
  cs.sort(function(a, b) { return a[0] - b[0]; });
  aa.sort(function(a, b) { return a[0] - b[0]; });
  var out = [];
  for (i = 0; i < m; i++) {
    var t = i / (m - 1), r = 255, g = 255, b = 255, u = 0;
    var cA = cs.length ? cs[0][1] : "#ffffff";
    var cB = cs.length ? cs[cs.length - 1][1] : "#ffffff";
    if (cs.length) {
      for (var j = 0; j < cs.length - 1; j++) {
        if (cs[j][0] <= t && t <= cs[j + 1][0]) {
          cA = cs[j][1]; cB = cs[j + 1][1];
          var span = cs[j + 1][0] - cs[j][0];
          u = span <= 0 ? 0 : (t - cs[j][0]) / span;
          break;
        }
      }
      var p0 = F.trailHex(cA), p1 = F.trailHex(cB);
      r = F.trailPyRound(p0[0] + (p1[0] - p0[0]) * u);
      g = F.trailPyRound(p0[1] + (p1[1] - p0[1]) * u);
      b = F.trailPyRound(p0[2] + (p1[2] - p0[2]) * u);
    }
    var a = 255;
    if (aa.length) a = F.trailEvalKeys(aa, t, 255.0);
    a = Math.max(0, Math.min(255, F.trailPyRound(a)));
    out.push([r, g, b, a]);
  }
  return out;
};
F.trailBuild = F.trailBuild || function(raw) {
  var cfg = F.trailNorm(raw);
  if (!cfg) return null;
  return {
    cfg: cfg,
    wlut: F.trailBakeCurve(cfg.widthCurve, 64),
    grad: F.trailBakeGrad(cfg.colorStops, cfg.alphaStops, 256),
    store: F.trailStoreNew()
  };
};
F.trailStoreNew = F.trailStoreNew || function() { return { hist: {}, now: 0 }; };
F.trailJump = F.trailJump || 150.0;
F.trailPhase = F.trailPhase || function(key) {
  var s = String(key), acc = 0;
  for (var i = 0; i < s.length; i++) acc += s.charCodeAt(i);
  return (acc % 1000) / 1000;
};
F.trailPush = F.trailPush || function(store, key, x, y, z, cfg) {
  var now = store.now;
  var maxp = Math.max(2, Math.floor(+cfg.maxPoints || 32));
  var life = Math.max(0.05, +cfg.lifetime || 0);
  var md = Math.max(0, +cfg.minDist || 0);
  var mt = Math.max(0, +cfg.minTime || 0);
  var jit = Math.max(0, Math.min(1, +cfg.lifetimeJitter || 0));
  var dist = cfg.emitMode === "distance";
  var seclen = Math.max(0, +cfg.sectionLength || 0);
  if (jit > 0 && key !== "emitter") {
    life = Math.max(0.05, life * (1 - jit * F.trailPhase(key)));
  }
  var h = store.hist[key];
  if (!h) { h = []; store.hist[key] = h; }
  var J2 = F.trailJump * F.trailJump;
  if (dist && seclen > 0) {
    if (!h.length) { h.push({ x: x, y: y, z: z, t: now }); return; }
    var a = h[h.length - 1];
    var dx = x - a.x, dy = y - a.y, dz = z - a.z;
    var d2 = dx * dx + dy * dy + dz * dz;
    if (d2 > J2) { h.length = 0; h.push({ x: x, y: y, z: z, t: now }); return; }
    var d = Math.sqrt(d2);
    if (d <= 0) return;
    var ux = dx / d, uy = dy / d, uz = dz / d;
    var ax = a.x, ay = a.y, az = a.z;
    var cnt = Math.min(Math.floor(d / seclen), maxp * 2), k;
    for (k = 0; k < cnt; k++) {
      ax += ux * seclen; ay += uy * seclen; az += uz * seclen;
      h.push({ x: ax, y: ay, z: az, t: now });
      while (h.length > maxp) h.shift();
    }
    return;
  }
  if (h.length) {
    var l = h[h.length - 1];
    var ex = x - l.x, ey = y - l.y, ez = z - l.z;
    var e2 = ex * ex + ey * ey + ez * ez;
    if (e2 > J2) {
      h.length = 0;
    } else if (dist) {
      /* sectionLength 0: every update (Trail2D-tick FIFO) */
    } else {
      if (mt > 0 && now - l.t < mt) return;
      if (md > 0 && e2 < md * md) return;
    }
  }
  h.push({ x: x, y: y, z: z, t: now });
  while (h.length > maxp) h.shift();
  if (!dist) {
    while (h.length > 1 && now - h[0].t > life) h.shift();
  }
};
F.trailSweep = F.trailSweep || function(store, n, emitterOnly) {
  for (var k in store.hist) {
    if (!store.hist.hasOwnProperty(k)) continue;
    if (k === "emitter") continue;
    var idx = +k;
    if (emitterOnly || !(idx >= 0) || idx >= n) delete store.hist[k];
  }
};
F.trailPushOne = F.trailPushOne || function(tb, key, x, y, z) {
  F.trailPush(tb.store, key, x, y, z, tb.cfg);
};
F.trailWidthAt = F.trailWidthAt || function(t, cfg, wlut) {
  var curve = 1.0;
  try {
    curve = +wlut[Math.max(0, Math.min(63, Math.floor(t * 63)))];
    if (!isFinite(curve)) curve = 1.0;
  } catch (e) { curve = 1.0; }
  var w = (cfg.widthStart + (cfg.widthEnd - cfg.widthStart) * t) * curve * cfg.widthMult;
  if (cfg.taperHead) w *= Math.min(1, Math.max(0, t / 0.06));
  if (cfg.taperTail) w *= Math.min(1, Math.max(0, (1 - t) / 0.06));
  return Math.max(0, w);
};
F.trailLut = F.trailLut || function(grad, t) {
  try {
    var c = grad[Math.max(0, Math.min(255, Math.floor(t * 255)))];
    return [c[0], c[1], c[2], c[3]];
  } catch (e) { return [255, 255, 255, 255]; }
};
F.trailOuter = F.trailOuter || function(gr, edgeHex, k) {
  var e = F.trailHex(edgeHex);
  k = Math.max(0, +k || 0);
  return [
    Math.min(255, (gr[0] + (e[0] - gr[0]) * 0.5) * k),
    Math.min(255, (gr[1] + (e[1] - gr[1]) * 0.5) * k),
    Math.min(255, (gr[2] + (e[2] - gr[2]) * 0.5) * k)
  ];
};
F.trailCore = F.trailCore || function(gr, coreHex, k) {
  var r, g, b;
  if (String(coreHex || "").trim()) {
    var c = F.trailHex(coreHex);
    r = c[0]; g = c[1]; b = c[2];
  } else {
    r = Math.min(255, gr[0] * 1.25 + 20);
    g = Math.min(255, gr[1] * 1.25 + 20);
    b = Math.min(255, gr[2] * 1.25 + 20);
  }
  k = Math.max(0, +k || 0);
  return [Math.min(255, r * k), Math.min(255, g * k), Math.min(255, b * k)];
};
F.trailFlick = F.trailFlick || function(nowS, hz, amt, ph) {
  if (!(amt > 0) || !(hz > 0)) return 1;
  return 1 - amt * 0.5 * (1 + Math.sin(2 * Math.PI * (hz * nowS + ph)));
};
F.trailStride = F.trailStride || function(n, m) {
  if (n <= 1) return [0];
  if (n - 1 <= m) { var o = [], i; for (i = 0; i < n; i++) o.push(i); return o; }
  var step = (n - 1) / m, idx = [], k;
  for (k = 0; k <= m; k++) idx.push(Math.round(k * step));
  idx[idx.length - 1] = n - 1;
  var seen = {}, out = [];
  for (k = 0; k < idx.length; k++) {
    if (!seen[idx[k]]) { seen[idx[k]] = 1; out.push(idx[k]); }
  }
  out.sort(function(a, b) { return a - b; });
  return out;
};
F.trailRibbon2D = F.trailRibbon2D || function(g, pts, tb, key) {
  var cfg = tb.cfg, n = pts.length;
  var idx = F.trailStride(n, 16), S = idx.length;
  if (S < 2) return;
  var fl = F.trailFlick(tb.store.now, cfg.flickerHz, cfg.flickerAmt, F.trailPhase(key));
  var X = [], Y = [], NX = [], NY = [], W = [], E = [], C = [], A = [];
  var lx = 1, ly = 0, s, p, t;
  for (s = 0; s < S; s++) {
    p = pts[idx[s]];
    t = 1 - idx[s] / (n - 1);
    var p0 = pts[idx[s > 0 ? s - 1 : 0]], p1 = pts[idx[s < S - 1 ? s + 1 : S - 1]];
    var dx = p1.x - p0.x, dy = p1.y - p0.y;
    var dl = Math.sqrt(dx * dx + dy * dy);
    if (dl > 1e-6) { lx = -dy / dl; ly = dx / dl; }
    var w = Math.max(+cfg.minScreenWidth || 0, F.trailWidthAt(t, cfg, tb.wlut));
    var c = F.trailLut(tb.grad, t);
    var ao = Math.max(0, Math.min(1, (c[3] / 255) * fl));
    X.push(p.x); Y.push(p.y); NX.push(lx); NY.push(ly); W.push(w);
    E.push(F.trailOuter([c[0], c[1], c[2]], cfg.edgeColor, cfg.intensity));
    C.push(F.trailCore([c[0], c[1], c[2]], cfg.coreColor, cfg.intensity));
    A.push(ao);
  }
  function quad(half, col, alp) {
    for (var q = 0; q < S - 1; q++) {
      var h0 = half(q), h1 = half(q + 1);
      var c0 = col(q), c1 = col(q + 1);
      var am = (alp(q) + alp(q + 1)) / 2;
      if (am <= 0) continue;
      g.beginFill(((Math.round((c0[0] + c1[0]) / 2) << 16) |
                   (Math.round((c0[1] + c1[1]) / 2) << 8) |
                   Math.round((c0[2] + c1[2]) / 2)), am);
      g.drawPolygon([X[q] + NX[q] * h0, Y[q] + NY[q] * h0,
                     X[q] - NX[q] * h0, Y[q] - NY[q] * h0,
                     X[q + 1] - NX[q + 1] * h1, Y[q + 1] - NY[q + 1] * h1,
                     X[q + 1] + NX[q + 1] * h1, Y[q + 1] + NY[q + 1] * h1]);
      g.endFill();
    }
  }
  var gw = Math.max(0, +cfg.glowWidth || 0);
  var ga = Math.max(0, Math.min(1, +cfg.glowAlpha || 0));
  if (gw > 0 && ga > 0) {
    quad(function(s) { return W[s] / 2 + gw; },
         function(s) { return E[s]; },
         function(s) { return A[s] * ga; });
  }
  quad(function(s) { return W[s] / 2; },
       function(s) { return E[s]; },
       function(s) { return A[s]; });
  var cw = Math.max(0, Math.min(1, +cfg.coreWidth || 0));
  if (cw > 0) {
    quad(function(s) { return (W[s] / 2) * cw; },
         function(s) { return C[s]; },
         function(s) { return A[s]; });
  }
};
F.trailDraw2D = F.trailDraw2D || function(data) {
  var tb = data.trailB;
  if (!tb || !tb.cfg) return;
  F.trailSweep(tb.store, data.particles.length, tb.cfg.source === "emitter");
  if (!data.particleContainer) return;
  if (!data.trailGfx || !data.trailGfx.parent) {
    data.trailGfx = new PIXI.Graphics();
    data.particleContainer.addChild(data.trailGfx);
  }
  var g = data.trailGfx;
  g.clear();
  var drawn = 0, key, pts;
  for (key in tb.store.hist) {
    if (drawn >= 384) break;
    pts = tb.store.hist[key];
    if (!pts || pts.length < 2) continue;
    F.trailRibbon2D(g, pts, tb, key);
    drawn++;
  }
};
// </carrot-trails-helpers>"""

TRAIL_3D_JS = r"""// <carrot-trails-3d>
F.trailRibbonIndex = F.trailRibbonIndex || function() {
  if (F._trailIdx) return F._trailIdx;
  var idx = [], s, q;
  for (s = 0; s < 16; s++) {
    var b = s * 7;
    for (q = 0; q < 6; q++) {
      var a = b + q, c = b + q + 7;
      idx.push(a, c, a + 1, a + 1, c, c + 1);
    }
  }
  F._trailIdx = idx;
  return idx;
};
F.trailStrip3D = F.trailStrip3D || function(mesh, pts, tb, key, camPos) {
  var cfg = tb.cfg, n = pts.length;
  var idx = F.trailStride(n, 16), S = idx.length;
  if (S < 2) { mesh.visible = false; return; }
  var pos = mesh.geometry.getAttribute("position");
  var col = mesh.geometry.getAttribute("color");
  var pa = pos.array, ca = col.array;
  var fl = F.trailFlick(tb.store.now, cfg.flickerHz, cfg.flickerAmt, F.trailPhase(key));
  var sx = 1, sy = 0, sz = 0, s, v;
  for (s = 0; s < 17; s++) {
    var si = s < S ? s : S - 1;
    var src = pts[idx[si]];
    var t = S < 2 ? 0 : 1 - idx[si] / (n - 1);
    var w = Math.max(+cfg.minScreenWidth || 0, F.trailWidthAt(t, cfg, tb.wlut));
    var c = F.trailLut(tb.grad, t);
    var ao = Math.max(0, Math.min(1, (c[3] / 255) * fl));
    var er = F.trailOuter([c[0], c[1], c[2]], cfg.edgeColor, cfg.intensity);
    var cr = F.trailCore([c[0], c[1], c[2]], cfg.coreColor, cfg.intensity);
    var p0 = pts[idx[si > 0 ? si - 1 : 0]], p1 = pts[idx[si < S - 1 ? si + 1 : S - 1]];
    var dx = p1.x - p0.x, dy = p1.y - p0.y, dz = p1.z - p0.z;
    var dl = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (dl > 1e-6) {
      dx /= dl; dy /= dl; dz /= dl;
      var vx = camPos.x - src.x, vy = camPos.y - src.y, vz = camPos.z - src.z;
      var vl = Math.sqrt(vx * vx + vy * vy + vz * vz) || 1;
      vx /= vl; vy /= vl; vz /= vl;
      var qx = dy * vz - dz * vy, qy = dz * vx - dx * vz, qz = dx * vy - dy * vx;
      var ql = Math.sqrt(qx * qx + qy * qy + qz * qz);
      if (ql > 1e-6) { sx = qx / ql; sy = qy / ql; sz = qz / ql; }
    }
    var hw = w / 2;
    var gw = hw + Math.max(0, +cfg.glowWidth || 0);
    var ga = ao * Math.max(0, Math.min(1, +cfg.glowAlpha || 0));
    var cw = hw * Math.max(0, Math.min(1, +cfg.coreWidth || 0));
    var offs = [-gw, -hw, -cw, 0, cw, hw, gw];
    var cols = [
      [er[0], er[1], er[2], ga], [er[0], er[1], er[2], ao],
      [cr[0], cr[1], cr[2], ao], [cr[0], cr[1], cr[2], ao],
      [cr[0], cr[1], cr[2], ao], [er[0], er[1], er[2], ao],
      [er[0], er[1], er[2], ga]
    ];
    for (v = 0; v < 7; v++) {
      var o = offs[v], vi = (s * 7 + v) * 3, ci = (s * 7 + v) * 4;
      pa[vi] = src.x + sx * o; pa[vi + 1] = src.y + sy * o; pa[vi + 2] = src.z + sz * o;
      ca[ci] = cols[v][0] / 255; ca[ci + 1] = cols[v][1] / 255;
      ca[ci + 2] = cols[v][2] / 255; ca[ci + 3] = cols[v][3] / 255;
    }
  }
  pos.needsUpdate = true;
  col.needsUpdate = true;
  mesh.geometry.setDrawRange(0, Math.max(0, S - 1) * 36);
  mesh.visible = true;
};
F.trailDraw3D = F.trailDraw3D || function(data, camera, blending) {
  var tb = data.trailB;
  if (!tb || !tb.cfg || !data.particleGroup) return;
  F.trailSweep(tb.store, data.particles.length, tb.cfg.source === "emitter");
  var T = (typeof THREE !== "undefined") ? THREE : null;
  var b = F.threeBlendFor(blending, T);
  if (!data.trailMat || data._trailBlend !== blending) {
    data._trailBlend = blending;
    if (!data.trailMat && T) {
      data.trailMat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 1, depthWrite: false, side: THREE.DoubleSide });
    }
    if (data.trailMat) {
      data.trailMat.blending = b.blending;
      if (b.equation) {
        data.trailMat.blendEquation = b.equation;
        if (b.src !== null && b.dst !== null) { data.trailMat.blendSrc = b.src; data.trailMat.blendDst = b.dst; }
      }
      data.trailMat.needsUpdate = true;
    }
  }
  if (!data.trailPool && T && data.trailMat) {
    data.trailPool = [];
    for (var r = 0; r < 128; r++) {
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(17 * 7 * 3), 3).setUsage(THREE.DynamicDrawUsage));
      g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(17 * 7 * 4), 4).setUsage(THREE.DynamicDrawUsage));
      g.setIndex(F.trailRibbonIndex());
      var mesh = new THREE.Mesh(g, data.trailMat);
      mesh.frustumCulled = false;
      mesh.visible = false;
      mesh.renderOrder = 5;
      data.particleGroup.add(mesh);
      data.trailPool.push(mesh);
    }
  }
  if (!data.trailPool || !camera) {
    if (data.trailPool) {
      for (var i = 0; i < data.trailPool.length; i++) data.trailPool[i].visible = false;
    }
    return;
  }
  try { camera.updateMatrixWorld(true); } catch (e) {}
  var cp = F._trCam || (F._trCam = new THREE.Vector3());
  try { cp.setFromMatrixPosition(camera.matrixWorld); }
  catch (e2) { cp.set(0, 0, 500); }
  var used = 0, key, pts;
  for (key in tb.store.hist) {
    if (used >= data.trailPool.length) break;
    pts = tb.store.hist[key];
    if (!pts || pts.length < 2) continue;
    F.trailStrip3D(data.trailPool[used], pts, tb, key, cp);
    used++;
  }
  for (i = used; i < data.trailPool.length; i++) data.trailPool[i].visible = false;
};
F.trailDispose3D = F.trailDispose3D || function(data) {
  try {
    if (data.trailPool) {
      for (var i = 0; i < data.trailPool.length; i++) {
        var m = data.trailPool[i];
        if (m.parent) m.parent.remove(m);
        if (m.geometry && m.geometry.dispose) m.geometry.dispose();
      }
      data.trailPool = null;
    }
    if (data.trailMat && data.trailMat.dispose) data.trailMat.dispose();
    data.trailMat = null;
  } catch (e) {}
};
// </carrot-trails-3d>"""


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
    doc = json.loads(raw)
    if doc.get("version") != "0.1.2":
        print("ALREADY-PATCHED (version %s)" % doc.get("version"))
        return
    changed = []

    for oname, ns in (("AvancedParticleEmitter2D", "2D"),
                      ("AvancedParticleEmitter3D", "3D")):
        hits = _chunks_of(doc, oname)

        # 1) pure helpers next to the RNG defs
        defs_hits = [(ev, t) for ev, t in hits
                     if "F.srand = F.srand || function(seed) {" in t]
        assert len(defs_hits) == 1, "%s defs chunk x%d" % (ns, len(defs_hits))
        ev, text = defs_hits[0]
        assert MARK_A not in text, ns + " helpers already present"
        block = _indent(TRAIL_CORE_JS)
        if ns == "3D":
            block += "\n" + _indent(TRAIL_3D_JS)
        text = _replace_once(
            text,
            "F.srand = F.srand || function(seed) {",
            block + "\n  F.srand = F.srand || function(seed) {",
            "%s trail defs" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s defs" % ns, text))

        # 2) normalizeEmitter passes trails through
        hits = _chunks_of(doc, oname)
        norm_old = ("      fields: (src.fields && typeof src.fields"
                    " === \"object\") ? src.fields : null,")
        norm_hits = [(ev, t) for ev, t in hits if norm_old in t]
        assert len(norm_hits) == 1, "%s normalize chunk x%d" % (ns, len(norm_hits))
        ev, text = norm_hits[0]
        text = _replace_once(
            text,
            norm_old,
            norm_old + "\n"
            "      trails: (src.trails && typeof src.trails"
            " === \"object\") ? src.trails : null,",
            "%s normalize trails" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s normalize" % ns, text))

        # 3) lazy trail build + per-frame vars next to the tracks build
        hits = _chunks_of(doc, oname)
        if ns == "2D":
            tb_old = ("if (!data.tracks) data.tracks = F.buildTracks(kf);\n"
                      "var Ts = data.tracks.T; var bT = data.tracks.baseT;")
            tb_new = (tb_old + "\n"
                      "if (!data.trailB && data.emitter && data.emitter.trails)"
                      " data.trailB = F.trailBuild(data.emitter.trails);\n"
                      "var _trailOn = !!(data.trailB && data.trailB.cfg);\n"
                      "var _trailHide = _trailOn && !!data.trailB.cfg.hideParticle;\n"
                      "if (_trailOn) { data.trailB.store.now += dt;"
                      " if (data.trailB.cfg.source === \"emitter\")"
                      " F.trailPushOne(data.trailB, \"emitter\", cx, cy, 0); }")
        else:
            tb_old = ("if (!data.tracks) data.tracks = F.buildTracks(kf,"
                      " emitter.rotationMode);\n"
                      "var Ts = data.tracks.T; var bT = data.tracks.baseT;")
            tb_new = (tb_old + "\n"
                      "if (!data.trailB && data.emitter && data.emitter.trails)"
                      " data.trailB = F.trailBuild(data.emitter.trails);\n"
                      "var _trailOn = !!(data.trailB && data.trailB.cfg);\n"
                      "var _trailHide = _trailOn && !!data.trailB.cfg.hideParticle;\n"
                      "if (_trailOn) { data.trailB.store.now += dt;"
                      " if (data.trailB.cfg.source === \"emitter\")"
                      " F.trailPushOne(data.trailB, \"emitter\", cx, cy, cz); }")
        upd_hits = [(ev, t) for ev, t in hits if tb_old in t]
        assert len(upd_hits) == 1, "%s tracks chunk x%d" % (ns, len(upd_hits))
        ev, text = upd_hits[0]
        text = _replace_once(text, tb_old, tb_new, "%s trail vars" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s vars" % ns, text))

        # 4) history push + dot hiding inside the main loop
        hits = _chunks_of(doc, oname)
        if ns == "2D":
            draw_old = ("  var dObj = p.displayObj;\n"
                        "  dObj.position.set(p.x, p.y);")
            draw_new = ("  if (_trailOn && data.trailB.cfg.source !== \"emitter\")"
                        " F.trailPushOne(data.trailB, i, p.x, p.y, 0);\n"
                        + draw_old +
                        "\n  if (_trailHide) { dObj.visible = false; continue; }\n"
                        "  if (!dObj.visible) dObj.visible = true;")
        else:
            draw_old = ("    var s = Math.max(size, 0.01);\n"
                        "    p.lastSize = s;")
            draw_new = (draw_old +
                        "\n    if (_trailOn && data.trailB.cfg.source"
                        " !== \"emitter\")"
                        " F.trailPushOne(data.trailB, i, p.x, p.y, p.z);")
            hide_old = ("    if (p.inst) {\n"
                        "      F.writeInstance(data, _shpI,")
            hide_new = ("    if (_trailHide) { if (p.mesh) p.mesh.visible = false; }\n"
                        "    else if (p.mesh && !p.mesh.visible)"
                        " { p.mesh.visible = true; }\n"
                        "    if (_trailHide) continue;\n"
                        + hide_old)
        loop_hits = [(ev, t) for ev, t in hits if draw_old in t]
        assert len(loop_hits) == 1, "%s loop chunk x%d" % (ns, len(loop_hits))
        ev, text = loop_hits[0]
        text = _replace_once(text, draw_old, draw_new, "%s loop" % ns)
        if ns == "3D":
            text = _replace_once(text, hide_old, hide_new, "3D hide")
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s loop" % ns, text))

        # 5) ribbon draw after the main loop
        hits = _chunks_of(doc, oname)
        if ns == "2D":
            end_old = "}\n\n// Rebuild guides if relevant"
            end_new = ("}\n"
                       "if (_trailOn) F.trailDraw2D(data);\n"
                       "\n// Rebuild guides if relevant")
        else:
            end_old = ("// Toggle particle rendering (simulation continues regardless)\n"
                       "if (data.particleGroup) data.particleGroup.visible = renderEnabled;")
            end_new = ("if (_trailOn) F.trailDraw3D(data,"
                       " (typeof threeCamera !== \"undefined\" ? threeCamera : null),"
                       " (typeof blendingMode === \"string\" ? blendingMode : \"Normal\"));\n"
                       + end_old)
        end_hits = [(ev, t) for ev, t in hits if end_old in t]
        assert len(end_hits) == 1, "%s end chunk x%d" % (ns, len(end_hits))
        ev, text = end_hits[0]
        text = _replace_once(text, end_old, end_new, "%s draw" % ns)
        ev["inlineCode"] = text.split("\n")
        changed.append(("%s draw" % ns, text))

    # 6) ribbon-pool disposal in 3D onDestroy
    hits = _chunks_of(doc, "AvancedParticleEmitter3D")
    del_old = ("  if (d.particleGroup && d.particleGroup.parent)"
               " d.particleGroup.parent.remove(d.particleGroup);")
    del_hits = [(ev, t) for ev, t in hits if del_old in t]
    assert len(del_hits) == 1, "destroy chunk x%d" % len(del_hits)
    ev, text = del_hits[0]
    text = _replace_once(
        text, del_old,
        "  if (F && F.trailDispose3D) { try { F.trailDispose3D(d); }"
        " catch (e2) {} }\n" + del_old,
        "3D destroy")
    ev["inlineCode"] = text.split("\n")
    changed.append(("3D destroy", text))

    # 7) version bump
    assert doc.get("version") == "0.1.2", doc.get("version")
    doc["version"] = "0.2.0"

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
    print("PATCHED-OK ext=0.2.0")


if __name__ == "__main__":
    sys.exit(main())
