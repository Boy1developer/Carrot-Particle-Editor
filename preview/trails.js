/**
 * Trail/ribbon math for the fast preview — pure logic, no DOM/GL imports.
 * Mirrors editor/particle_studio.py (bake_curve/bake_gradient) and the
 * SimEngine._trail_push/update_trails semantics, so the browser preview
 * draws the same ribbons as the desktop viewport:
 * - t runs 0 at the head (newest point) to 1 at the tail (oldest)
 * - width(t) = lerp(widthStart, widthEnd, t) * widthCurve(t) * widthMult,
 *   taperHead/taperTail pinch the ends, minScreenWidth floors (px)
 * - color(t) comes from the baked 256-entry gradient LUT (head -> tail)
 * - distance mode lays exact sectionLength steps (Godot-style);
 *   time mode uses minDist/minTime gates + lifetime expiry
 * - slot reuse looks like a teleport: TRAIL_JUMP cuts the history
 */
export const TRAIL_JUMP = 150.0;
function num(v, fb) {
    const n = Number(v ?? fb);
    return isFinite(n) ? n : fb;
}
/** Python round(): banker's rounding (half to even) on doubles. */
export function pyRound(x) {
    const f = Math.floor(x);
    const d = x - f;
    if (d < 0.5)
        return f;
    if (d > 0.5)
        return f + 1;
    return f % 2 === 0 ? f : f + 1;
}
/** Mirror of particle_studio._parse_hex6 (bad input -> white). */
export function parseHex6(s) {
    let h = String(s ?? "#ffffff");
    if (h.charAt(0) === "#")
        h = h.slice(1);
    if (h.length === 3)
        h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    const n = parseInt(h.slice(0, 6), 16);
    if (!isFinite(n))
        return [255, 255, 255];
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/** Mirror of particle_studio._eval_keys (segment mode from the LEFT key). */
export function evalKeys(keys, t, def = 1.0) {
    const pts = [];
    try {
        for (const k of keys ?? []) {
            if (!Array.isArray(k) || k.length < 2)
                continue;
            const kk = k;
            pts.push([Number(kk[0]), Number(kk[1]),
                kk.length > 2 ? String(kk[2]).toLowerCase() : "smooth"]);
        }
    }
    catch {
        return def;
    }
    for (const p of pts)
        if (!isFinite(p[0]) || !isFinite(p[1]))
            return def;
    pts.sort((a, b) => a[0] - b[0]);
    if (!pts.length)
        return def;
    if (t <= pts[0][0])
        return pts[0][1];
    if (t >= pts[pts.length - 1][0])
        return pts[pts.length - 1][1];
    for (let j = 0; j < pts.length - 1; j++) {
        const [x0, y0, m] = pts[j];
        const [x1, y1] = pts[j + 1];
        if (x0 <= t && t <= x1) {
            const u = x1 <= x0 ? 0 : (t - x0) / (x1 - x0);
            if (m === "constant")
                return y0;
            if (m === "linear")
                return y0 + (y1 - y0) * u;
            const s = u * u * (3 - 2 * u);
            return y0 + (y1 - y0) * s;
        }
    }
    return pts[pts.length - 1][1];
}
/** Mirror of particle_studio.bake_curve (n samples, t = i/(n-1)). */
export function bakeCurve(keys, n = 64) {
    const m = Math.max(2, Math.floor(n));
    const out = [];
    for (let i = 0; i < m; i++)
        out.push(evalKeys(keys, i / (m - 1)));
    return out;
}
/** Mirror of particle_studio.bake_gradient (n RGBA int tuples). */
export function bakeGradient(colorStops, alphaStops, n = 256) {
    const m = Math.max(2, Math.floor(n));
    let cs = [];
    let aa = [];
    try {
        cs = (colorStops ?? [])
            .filter((k) => Array.isArray(k) && k.length >= 2)
            .map((k) => { const kk = k; return [Number(kk[0]), String(kk[1])]; });
        aa = (alphaStops ?? [])
            .filter((k) => Array.isArray(k) && k.length >= 2)
            .map((k) => { const kk = k; return [Number(kk[0]), Number(kk[1])]; });
        for (const p of cs)
            if (!isFinite(p[0]))
                throw new Error("bad");
        for (const p of aa)
            if (!isFinite(p[0]) || !isFinite(p[1]))
                throw new Error("bad");
    }
    catch {
        cs = [];
        aa = [];
    }
    cs.sort((a, b) => a[0] - b[0]);
    aa.sort((a, b) => a[0] - b[0]);
    const out = [];
    for (let i = 0; i < m; i++) {
        const t = i / (m - 1);
        let r = 255, g = 255, b = 255;
        if (cs.length) {
            let c0 = cs[0][1], c1 = cs[cs.length - 1][1], u = 0;
            for (let j = 0; j < cs.length - 1; j++) {
                if (cs[j][0] <= t && t <= cs[j + 1][0]) {
                    c0 = cs[j][1];
                    c1 = cs[j + 1][1];
                    const span = cs[j + 1][0] - cs[j][0];
                    u = span <= 0 ? 0 : (t - cs[j][0]) / span;
                    break;
                }
            }
            const [r0, g0, b0] = parseHex6(c0);
            const [r1, g1, b1] = parseHex6(c1);
            r = pyRound(r0 + (r1 - r0) * u);
            g = pyRound(g0 + (g1 - g0) * u);
            b = pyRound(b0 + (b1 - b0) * u);
        }
        let a = 255;
        if (aa.length)
            a = evalKeys(aa, t, 255.0);
        a = Math.max(0, Math.min(255, pyRound(a)));
        out.push([r, g, b, a]);
    }
    return out;
}
/** Normalize the optional trails block; null when inactive (mirrors trails_active). */
export function normTrailCfg(raw) {
    const d = (raw !== null && typeof raw === "object" ? raw : {});
    const enabled = Boolean(d.enabled);
    let maxPoints = Math.floor(num(d.maxPoints, 32));
    if (!isFinite(maxPoints))
        maxPoints = 32;
    if (!enabled || maxPoints <= 1)
        return null;
    const src = String(d.source ?? "particles");
    const mode = String(d.emitMode ?? "time");
    return {
        enabled,
        source: src === "emitter" ? "emitter" : "particles",
        maxPoints,
        lifetime: num(d.lifetime, 1.0),
        minDist: num(d.minDist, 4.0),
        minTime: num(d.minTime, 0.016),
        emitMode: mode === "distance" ? "distance" : "time",
        sectionLength: num(d.sectionLength, 8.0),
        hideParticle: d.hideParticle === undefined ? true : Boolean(d.hideParticle),
        lifetimeJitter: num(d.lifetimeJitter, 0.0),
        widthStart: num(d.widthStart, 8.0),
        widthEnd: num(d.widthEnd, 1.0),
        widthMult: num(d.widthMult, 1.0),
        widthCurve: (Array.isArray(d.widthCurve) ? d.widthCurve : [[0.0, 1.0], [1.0, 1.0]]),
        taperHead: Boolean(d.taperHead),
        taperTail: d.taperTail === undefined ? true : Boolean(d.taperTail),
        minScreenWidth: num(d.minScreenWidth, 2.5),
        edgeColor: String(d.edgeColor ?? "#ffffff"),
        coreColor: String(d.coreColor ?? ""),
        coreWidth: num(d.coreWidth, 0.35),
        glowWidth: num(d.glowWidth, 0.0),
        glowAlpha: num(d.glowAlpha, 0.0),
        flickerAmt: num(d.flickerAmt, 0.0),
        flickerHz: num(d.flickerHz, 8.0),
        intensity: num(d.intensity, 1.0),
        colorStops: (Array.isArray(d.colorStops) ? d.colorStops : [[0.0, "#ffffff"], [1.0, "#ffffff"]]),
        alphaStops: (Array.isArray(d.alphaStops) ? d.alphaStops : [[0.0, 255], [1.0, 0]]),
    };
}
/** Mirror of trail_render.width_at (full width before the px floor). */
export function widthAt(t, cfg, wlut) {
    let curve = 1.0;
    try {
        curve = Number(wlut[Math.max(0, Math.min(63, Math.floor(t * 63)))]);
        if (!isFinite(curve))
            curve = 1.0;
    }
    catch {
        curve = 1.0;
    }
    let w = (cfg.widthStart + (cfg.widthEnd - cfg.widthStart) * t) * curve * cfg.widthMult;
    if (cfg.taperHead)
        w *= Math.min(1, Math.max(0, t / 0.06));
    if (cfg.taperTail)
        w *= Math.min(1, Math.max(0, (1 - t) / 0.06));
    return Math.max(0, w);
}
/** Mirror of trail_render.floored_width. */
export function flooredWidth(t, cfg, wlut) {
    return Math.max(cfg.minScreenWidth, widthAt(t, cfg, wlut));
}
/** Mirror of trail_render.lut_color. */
export function lutColor(grad, t) {
    try {
        const c = grad[Math.max(0, Math.min(255, Math.floor(t * 255)))];
        return [c[0], c[1], c[2], c[3]];
    }
    catch {
        return [255, 255, 255, 255];
    }
}
/** Mirror of trail_render.flicker_factor. */
export function flickerFactor(nowS, hz, amt, phase) {
    if (amt <= 0 || hz <= 0)
        return 1;
    return 1 - amt * 0.5 * (1 + Math.sin(2 * Math.PI * (hz * nowS + phase)));
}
/** Edge-mixed outer color (mirror of trail_render.outer_color). */
export function outerColor(gradRgb, edgeHex, intensity) {
    const [er, eg, eb] = parseHex6(edgeHex);
    const k = Math.max(0, intensity);
    return [
        Math.min(255, (gradRgb[0] + (er - gradRgb[0]) * 0.5) * k),
        Math.min(255, (gradRgb[1] + (eg - gradRgb[1]) * 0.5) * k),
        Math.min(255, (gradRgb[2] + (eb - gradRgb[2]) * 0.5) * k),
    ];
}
/** Inner core color (mirror of trail_render.core_color). */
export function coreColor(gradRgb, coreHex, intensity) {
    let r, g, b;
    if (String(coreHex || "").trim()) {
        [r, g, b] = parseHex6(coreHex);
    }
    else {
        r = Math.min(255, gradRgb[0] * 1.25 + 20);
        g = Math.min(255, gradRgb[1] * 1.25 + 20);
        b = Math.min(255, gradRgb[2] * 1.25 + 20);
    }
    const k = Math.max(0, intensity);
    return [Math.min(255, r * k), Math.min(255, g * k), Math.min(255, b * k)];
}
/** Evenly strided indices covering [0, n-1] (mirror of stride_indices). */
export function strideIndices(n, maxSegs) {
    if (n <= 1)
        return [0];
    if (n - 1 <= maxSegs) {
        const out = [];
        for (let i = 0; i < n; i++)
            out.push(i);
        return out;
    }
    const step = (n - 1) / maxSegs;
    const idx = [];
    for (let i = 0; i <= maxSegs; i++)
        idx.push(Math.round(i * step));
    idx[idx.length - 1] = n - 1;
    return Array.from(new Set(idx)).sort((a, b) => a - b);
}
/** Per-trail history ring (mirror of SimEngine._trail_push/update_trails). */
export class TrailStore {
    constructor() {
        this.hist = new Map();
        this.now = 0;
    }
    clear() { this.hist.clear(); this.now = 0; }
    get time() { return this.now; }
    histories() {
        const out = [];
        for (const [key, pts] of this.hist)
            if (pts.length >= 2)
                out.push({ key, pts });
        return out;
    }
    jitterFrac(key) {
        const s = String(key);
        let acc = 0;
        for (let i = 0; i < s.length; i++)
            acc += s.charCodeAt(i);
        return (acc % 1000) / 1000;
    }
    push(key, x, y, z, cfg) {
        const now = this.now;
        const maxp = Math.max(2, Math.floor(Number(cfg.maxPoints) || 32));
        let life = Math.max(0.05, Number(cfg.lifetime) || 0);
        const md = Math.max(0, Number(cfg.minDist) || 0);
        const mt = Math.max(0, Number(cfg.minTime) || 0);
        const jit = Math.max(0, Math.min(1, Number(cfg.lifetimeJitter) || 0));
        const dist = cfg.emitMode === "distance";
        const seclen = Math.max(0, Number(cfg.sectionLength) || 0);
        if (jit > 0 && key !== "emitter") {
            life = Math.max(0.05, life * (1 - jit * this.jitterFrac(key)));
        }
        let h = this.hist.get(key);
        if (!h) {
            h = [];
            this.hist.set(key, h);
        }
        if (dist && seclen > 0) {
            if (!h.length) {
                h.push({ x, y, z, t: now });
                return;
            }
            const a = h[h.length - 1];
            const dx = x - a.x, dy = y - a.y, dz = z - a.z;
            const d2 = dx * dx + dy * dy + dz * dz;
            if (d2 > TRAIL_JUMP * TRAIL_JUMP) {
                h.length = 0;
                h.push({ x, y, z, t: now });
                return;
            }
            const d = Math.sqrt(d2);
            if (d <= 0)
                return;
            const ux = dx / d, uy = dy / d, uz = dz / d;
            let ax = a.x, ay = a.y, az = a.z;
            const n = Math.min(Math.floor(d / seclen), maxp * 2);
            for (let k = 0; k < n; k++) {
                ax += ux * seclen;
                ay += uy * seclen;
                az += uz * seclen;
                h.push({ x: ax, y: ay, z: az, t: now });
                while (h.length > maxp)
                    h.shift();
            }
            return;
        }
        if (h.length) {
            const l = h[h.length - 1];
            const dx = x - l.x, dy = y - l.y, dz = z - l.z;
            const d2 = dx * dx + dy * dy + dz * dz;
            if (d2 > TRAIL_JUMP * TRAIL_JUMP) {
                h.length = 0;
            }
            else if (dist) {
                /* sectionLength 0: every update (Trail2D-tick FIFO) */
            }
            else {
                if (mt > 0 && now - l.t < mt)
                    return;
                if (md > 0 && d2 < md * md)
                    return;
            }
        }
        h.push({ x, y, z, t: now });
        while (h.length > maxp)
            h.shift();
        if (!dist) {
            while (h.length > 1 && now - h[0].t > life)
                h.shift();
        }
    }
    /** Shared update for all sources (mirror of update_trails). */
    update(items, ex, ey, ez, dt, cfg) {
        this.now += dt;
        if (cfg.source === "emitter") {
            this.push("emitter", ex, ey, ez, cfg);
            const keep = this.hist.get("emitter");
            this.hist.clear();
            if (keep)
                this.hist.set("emitter", keep);
            return;
        }
        const alive = new Set();
        for (const it of items) {
            alive.add(it.key);
            this.push(it.key, it.x, it.y, it.z, cfg);
        }
        for (const k of Array.from(this.hist.keys())) {
            if (k !== "emitter" && !alive.has(k))
                this.hist.delete(k);
        }
    }
}
