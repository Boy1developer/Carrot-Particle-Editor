/**
 * ParticleFX Fast Preview — high-performance TypeScript particle engine.
 * - Preallocated SoA particle pool (zero per-frame allocation)
 * - 2D mode: flat canvas projection; 3D mode: orbit-camera perspective
 * - Keyframe morph across ALL states (size/color/opacity/speed lerp + discrete shape)
 * - Consumes GDParticleFX studio export format v1.0 (type "2d" / "3d")
 */

export interface Vec2 { x: number; y: number }

interface RGB { r: number; g: number; b: number }

interface EmitterCfg {
  flow: number; maxParticles: number; reservoir: number;
  mode: string; reverse: boolean; blending: string;
  gravity: { x: number; y: number; z: number };
  zone: {
    shape: string; radius: number; width: number; height: number;
    length: number; depth: number; rot: number; mode: string;
  };
  cone: { direction: number; directionY: number; spread: number };
}

interface Keyframe {
  dur: number; shape: string;
  size: number; sizeMax: number; color: RGB; opacity: number;
  minSpd: number; maxSpd: number; easing: string;
  modelRef: string;
}

const MAX_POOL = 4000;

function hexToRgb(hex: string): RGB {
  let h: string = (hex || "#ffffff").replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const n: number = parseInt(h, 16);
  if (!isFinite(n)) return { r: 255, g: 255, b: 255 };
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function easeFn(t: number, name: string): number {
  t = Math.max(0, Math.min(1, t));
  if (name === "ease-in") return t * t;
  if (name === "ease-out") return t * (2 - t);
  if (name === "ease-in-out") return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  return t;
}

function normMode(m: unknown): "infinite" | "burst" | "reservoir" {
  const key: string = String(m ?? "").trim().toLowerCase().replace(/[\s_-]+/g, "");
  if (key === "burst") return "burst";
  if (key === "oneshot" || key === "oneoff" || key === "finite" || key === "reservoir") return "reservoir";
  return "infinite";
}

function normZone(s: unknown): string {
  return String(s ?? "circle").trim().toLowerCase();
}

export class ParticleEngine {
  // SoA pool — allocated once
  private px = new Float32Array(MAX_POOL);
  private py = new Float32Array(MAX_POOL);
  private pz = new Float32Array(MAX_POOL);
  private vx = new Float32Array(MAX_POOL);
  private vy = new Float32Array(MAX_POOL);
  private vz = new Float32Array(MAX_POOL);
  private dx = new Float32Array(MAX_POOL);
  private dy = new Float32Array(MAX_POOL);
  private dz = new Float32Array(MAX_POOL);
  private gx = new Float32Array(MAX_POOL);
  private gy = new Float32Array(MAX_POOL);
  private gz = new Float32Array(MAX_POOL);
  private age = new Float32Array(MAX_POOL);
  private life = new Float32Array(MAX_POOL);
  private sizeRatio = new Float32Array(MAX_POOL);
  private spdRatio = new Float32Array(MAX_POOL);
  private count = 0;

  readonly cam = { yaw: 0.7, pitch: 0.42, zoom: 1.0, auto: true };
  is3D = false;
  private kf: Keyframe[] = [];
  private kfLife = 1.0;
  private effectRev = 0;
  private modelBlobs: Record<string, { mime: string; data: string }> = {};

  /** Bumped on every loadEffect — render layers rebuild guides on change. */
  get effectVersion(): number { return this.effectRev; }

  /** Emitter blend mode for the render layers (same fallbacks as the game runtime). */
  blendingMode(): string { return this.emitter.blending; }

  /** Copy of the normalized emission-zone config (for guide rendering). */
  zoneInfo(): { shape: string; radius: number; width: number; height: number;
    length: number; depth: number; rot: number; mode: string } {
    return { ...this.emitter.zone };
  }

  /** Copy of the normalized propagation-cone config (for guide rendering). */
  coneInfo(): { direction: number; directionY: number; spread: number } {
    return { ...this.emitter.cone };
  }

  private accum = 0;
  private bursted = false;
  private remaining = 0;
  private emitter!: EmitterCfg;

  get activeCount(): number { return this.count; }

  /** Read-only particle state for external renderers (e.g. the Three.js layer). */
  particleState(i: number): { x: number; y: number; z: number; age: number } {
    return { x: this.px[i], y: this.py[i], z: this.pz[i], age: this.age[i] };
  }

  loadEffect(eff: any): void {
    const raw: any = eff.emitter || {};
    const z: any = raw.emissionZone || {};
    const pc: any = raw.propagationCone || {};
    this.is3D = String(eff.type ?? "2d").toLowerCase() === "3d";
    this.emitter = {
      flow: Number(raw.flow ?? 40),
      maxParticles: Math.min(MAX_POOL, Number(raw.maxParticles ?? 300)),
      reservoir: Number(raw.reservoir ?? 50),
      mode: normMode(raw.mode),
      reverse: Boolean(raw.reverse),
      blending: String(raw.blendingMode ?? "Normal"),
      gravity: { x: Number(raw.gravity?.x ?? 0), y: Number(raw.gravity?.y ?? 0), z: Number(raw.gravity?.z ?? 0) },
      zone: {
        shape: normZone(z.shape),
        radius: Number(z.radius ?? 10),
        width: Number(z.width ?? 100),
        height: Number(z.height ?? 60),
        length: Number(z.length ?? 100),
        depth: Number(z.depth ?? 60),
        rot: Number(z.rotation ?? z.rotationZ ?? 0),
        mode: String(z.mode ?? "Surface").toLowerCase(),
      },
      cone: {
        direction: Number(pc.direction ?? pc.directionZ ?? 0),
        directionY: Number(pc.directionY ?? 0),
        spread: Number(pc.spread ?? 90),
      },
    };
    const states: any[] = Array.isArray(eff.states) ? eff.states : [];
    let prevShape = this.is3D ? "sphere" : "circle";
    this.kf = states.map((s: any): Keyframe => {
      const ap: any = s.appearance || {}, mv: any = s.movement || {};
      let shp: string = String(s.shape ?? "").toLowerCase() || prevShape;
      prevShape = shp;
      return {
        dur: Math.max(1e-6, Number(s.duration ?? 0.5)),
        shape: shp,
        size: Number(ap.size ?? 8),
        sizeMax: Number(ap.sizeMax ?? ap.size ?? 8),
        color: hexToRgb(String(ap.color ?? "#ffffff")),
        opacity: Number(ap.opacity ?? 255),
        minSpd: Number(mv.minSpeed ?? 0),
        maxSpd: Number(mv.maxSpeed ?? mv.minSpeed ?? 0),
        easing: String(s.easing ?? "linear"),
        modelRef: String((s.modelRefs as unknown[] | undefined)?.[0] ?? ""),
      };
    });
    // Embedded GLB/GLTF blobs for custom-model states. Replace (never merge
    // implicitly): the key is present only when the model set changed, and
    // an empty object clears previously cached blobs. Absent key keeps cache
    // so the 500ms live poll (which omits blobs when unchanged) never wipes.
    const md: unknown = (eff as { modelsData?: unknown }).modelsData;
    if (md !== undefined && md !== null && typeof md === "object") {
      const next: Record<string, { mime: string; data: string }> = {};
      for (const k of Object.keys(md as Record<string, unknown>)) {
        const v = (md as Record<string, any>)[k];
        if (v && typeof v.data === "string" && v.data.length > 0)
          next[k] = { mime: String(v.mime ?? ""), data: v.data };
      }
      this.modelBlobs = next;
    }
    // life excludes the death duration (extension semantics)
    this.kfLife = Math.max(0.1, this.kf.slice(0, -1).reduce((a, k) => a + k.dur, 0));
    this.count = 0; this.accum = 0; this.bursted = false;
    this.remaining = this.emitter.reservoir;
    this.effectRev++;
  }

  /** Locate interval k + eased local t + raw t (shape switches at raw>=0.5). */
  private locate(age: number): [number, number, number] {
    const n: number = Math.max(1, this.kf.length - 1);
    const t: number = Math.max(0, Math.min(age, this.kfLife));
    let acc = 0;
    for (let k = 0; k < n; k++) {
      const d: number = this.kf[k].dur;
      if (t < acc + d || k === n - 1) {
        const raw: number = d <= 0 ? 0 : Math.max(0, Math.min(1, (t - acc) / d));
        return [k, easeFn(raw, this.kf[k].easing), raw];
      }
      acc += d;
    }
    return [n - 1, 1, 1];
  }

  private sampleSpeed(age: number, i: number): number {
    const [k, e] = this.locate(age);
    const a: Keyframe = this.kf[k], b: Keyframe = this.kf[Math.min(k + 1, this.kf.length - 1)];
    const mn: number = a.minSpd + (b.minSpd - a.minSpd) * e;
    const mx: number = a.maxSpd + (b.maxSpd - a.maxSpd) * e;
    return mn + (mx - mn) * this.spdRatio[i];
  }

  private coneDir3(): [number, number, number] {
    const az: number = this.emitter.cone.direction * Math.PI / 180;
    const el: number = this.emitter.cone.directionY * Math.PI / 180;
    const bx: number = Math.cos(el) * Math.cos(az);
    const by: number = Math.sin(el);
    const bz: number = Math.cos(el) * Math.sin(az);
    const half: number = (this.emitter.cone.spread / 2) * Math.PI / 180;
    const th: number = Math.random() * Math.PI * 2;
    const r: number = Math.tan(half) * Math.sqrt(Math.random());
    let ux = 0, uy = 1, uz = 0;
    if (Math.abs(by) > 0.95) { ux = 1; uy = 0; }
    let cx1: number = by * uz - bz * uy, cy1: number = bz * ux - bx * uz, cz1: number = bx * uy - by * ux;
    const n1: number = Math.hypot(cx1, cy1, cz1) || 1;
    ux = cx1 / n1; uy = cy1 / n1; uz = cz1 / n1;
    const vx2: number = by * uz - bz * uy, vy2: number = bz * ux - bx * uz, vz2: number = bx * uy - by * ux;
    const ca: number = Math.cos(th) * r, sa: number = Math.sin(th) * r;
    const dx: number = bx + ux * ca + vx2 * sa;
    const dy: number = by + uy * ca + vy2 * sa;
    const dz: number = bz + uz * ca + vz2 * sa;
    const n: number = Math.hypot(dx, dy, dz) || 1;
    return [dx / n, dy / n, dz / n];
  }

  private spawnAt(cx: number, cy: number): void {
    if (this.count >= Math.min(this.emitter.maxParticles, MAX_POOL)) return;
    if (!this.kf.length) return;
    const e: EmitterCfg = this.emitter;
    const i: number = this.count++;
    const jitter: number = 0.9 + Math.random() * 0.2;
    this.life[i] = this.kfLife * jitter;
    this.sizeRatio[i] = Math.random();
    this.spdRatio[i] = Math.random();
    this.gx[i] = 0; this.gy[i] = 0; this.gz[i] = 0;
    const spd: number = this.sampleSpeed(0, i);
    if (this.is3D) {
      const z = e.zone;
      const rot: number = z.rot * Math.PI / 180;
      const cr: number = Math.cos(rot), sr: number = Math.sin(rot);
      let sx = 0, sy = 0, sz = 0;
      if (z.shape === "sphere" || z.shape === "circle") {
        const th: number = Math.random() * Math.PI * 2;
        const ph: number = Math.acos(2 * Math.random() - 1);
        const rr: number = z.radius * Math.cbrt(Math.random());
        sx = rr * Math.sin(ph) * Math.cos(th); sy = rr * Math.cos(ph); sz = rr * Math.sin(ph) * Math.sin(th);
      } else if (z.shape === "box" || z.shape === "rectangle") {
        sx = (Math.random() - 0.5) * z.width; sy = (Math.random() - 0.5) * z.height; sz = (Math.random() - 0.5) * z.depth;
        const rx: number = sx * cr - sy * sr, ry: number = sx * sr + sy * cr;
        sx = rx; sy = ry;
      } else if (z.shape === "line") {
        sx = (Math.random() - 0.5) * z.length;
        const rx: number = sx * cr; sy = sx * sr; sx = rx;
      }
      const [dx, dy, dz] = this.coneDir3();
      this.dx[i] = e.reverse ? -dx : dx;
      this.dy[i] = e.reverse ? -dy : dy;
      this.dz[i] = e.reverse ? -dz : dz;
      if (e.reverse) {
        const dist: number = spd * this.life[i];
        this.px[i] = sx + dx * dist; this.py[i] = sy + dy * dist; this.pz[i] = sz + dz * dist;
      } else {
        this.px[i] = sx; this.py[i] = sy; this.pz[i] = sz;
      }
      this.vx[i] = this.dx[i] * spd; this.vy[i] = this.dy[i] * spd; this.vz[i] = this.dz[i] * spd;
    } else {
      const half: number = e.cone.spread / 2;
      const ang: number = (e.cone.direction + (Math.random() * 2 - 1) * half) * Math.PI / 180;
      let dx: number = Math.cos(ang), dy: number = Math.sin(ang);
      const z = e.zone;
      const rot: number = (z.rot || 0) * Math.PI / 180;
      const cr: number = Math.cos(rot), sr: number = Math.sin(rot);
      let lx = 0, ly = 0;
      if (z.shape === "circle" || z.shape === "sphere") {
        const a: number = Math.random() * Math.PI * 2;
        if (z.mode === "edge") { lx = Math.cos(a) * z.radius; ly = Math.sin(a) * z.radius; }
        else { const r: number = Math.sqrt(Math.random()) * z.radius; lx = Math.cos(a) * r; ly = Math.sin(a) * r; }
      } else if (z.shape === "rectangle" || z.shape === "box") {
        if (z.mode === "edge") {
          const per: number = 2 * (z.width + z.height), d: number = Math.random() * per;
          if (d < z.width) { lx = d - z.width / 2; ly = -z.height / 2; }
          else if (d < z.width + z.height) { lx = z.width / 2; ly = (d - z.width) - z.height / 2; }
          else if (d < 2 * z.width + z.height) { lx = z.width / 2 - (d - z.width - z.height); ly = z.height / 2; }
          else { lx = -z.width / 2; ly = z.height / 2 - (d - 2 * z.width - z.height); }
        } else { lx = (Math.random() - 0.5) * z.width; ly = (Math.random() - 0.5) * z.height; }
      } else if (z.shape === "line") {
        lx = (Math.random() - 0.5) * z.length;
      }
      const ox: number = lx * cr - ly * sr, oy: number = lx * sr + ly * cr;
      if (e.reverse) { dx = -dx; dy = -dy; }
      this.dx[i] = dx; this.dy[i] = dy; this.dz[i] = 0;
      if (e.reverse) {
        const dist: number = spd * this.life[i];
        this.px[i] = cx + ox + dx * dist; this.py[i] = cy + oy + dy * dist;
      } else {
        this.px[i] = cx + ox; this.py[i] = cy + oy;
      }
      this.pz[i] = 0;
      this.vx[i] = dx * spd; this.vy[i] = dy * spd; this.vz[i] = 0;
    }
    this.age[i] = 0;
  }

  private kill(i: number): void {
    const l: number = --this.count;
    if (i !== l) {
      this.px[i] = this.px[l]; this.py[i] = this.py[l]; this.pz[i] = this.pz[l];
      this.vx[i] = this.vx[l]; this.vy[i] = this.vy[l]; this.vz[i] = this.vz[l];
      this.dx[i] = this.dx[l]; this.dy[i] = this.dy[l]; this.dz[i] = this.dz[l];
      this.gx[i] = this.gx[l]; this.gy[i] = this.gy[l]; this.gz[i] = this.gz[l];
      this.age[i] = this.age[l]; this.life[i] = this.life[l];
      this.sizeRatio[i] = this.sizeRatio[l]; this.spdRatio[i] = this.spdRatio[l];
    }
  }

  update(dt: number, cx: number, cy: number): void {
    const e: EmitterCfg = this.emitter;
    if (e.mode === "burst") {
      if (!this.bursted) {
        this.bursted = true;
        const n: number = Math.min(e.reservoir, e.maxParticles, MAX_POOL);
        for (let k = 0; k < n; k++) this.spawnAt(cx, cy);
      }
    } else if (e.mode === "reservoir") {
      if (!this.bursted) {
        this.accum += e.flow * dt;
        while (this.accum >= 1 && this.remaining > 0) {
          this.accum -= 1;
          this.spawnAt(cx, cy); this.remaining--;
        }
        if (this.remaining <= 0) this.bursted = true;
      }
    } else {
      this.accum += e.flow * dt;
      while (this.accum >= 1) {
        this.accum -= 1;
        this.spawnAt(cx, cy);
      }
    }
    const gravScale: number = this.is3D ? 1.0 : 0.4;
    const gx: number = e.gravity.x * dt * gravScale;
    const gy: number = e.gravity.y * dt * gravScale;
    const gz: number = e.gravity.z * dt * gravScale;
    for (let i = this.count - 1; i >= 0; i--) {
      this.age[i] += dt;
      if (this.age[i] >= this.life[i]) { this.kill(i); continue; }
      this.gx[i] += gx; this.gy[i] += gy; this.gz[i] += gz;
      const spd: number = this.sampleSpeed(this.age[i], i);
      this.vx[i] = this.dx[i] * spd + this.gx[i];
      this.vy[i] = this.dy[i] * spd + this.gy[i];
      this.vz[i] = this.dz[i] * spd + this.gz[i];
      this.px[i] += this.vx[i] * dt; this.py[i] += this.vy[i] * dt; this.pz[i] += this.vz[i] * dt;
    }
  }

  /** Model ref sampled like shape (mid-segment flip), "" when none. */
  modelRefAt(age: number): string {
    if (!this.kf.length) return "";
    const [k, , raw] = this.locate(age);
    const a: Keyframe = this.kf[k], b: Keyframe = this.kf[Math.min(k + 1, this.kf.length - 1)];
    return raw >= 0.5 ? b.modelRef : a.modelRef;
  }

  /** Shape cross-fade companion during the flip window, else null.
   * Mirrors the desktop/C++ window: raw segment time in (0.25, 0.75). */
  morphAt(age: number): {
    aShape: string; bShape: string; aRef: string; bRef: string; t: number;
  } | null {
    if (this.kf.length < 2) return null;
    const [k, , raw] = this.locate(age);
    if (!(raw > 0.25 && raw < 0.75) || k < 0 || k + 1 >= this.kf.length)
      return null;
    const a: Keyframe = this.kf[k], b: Keyframe = this.kf[k + 1];
    return {
      aShape: a.shape, bShape: b.shape, aRef: a.modelRef, bRef: b.modelRef,
      t: (raw - 0.25) / 0.5,
    };
  }

  /** Distinct non-empty model refs across keyframes. */
  customRefs(): string[] {
    const out: string[] = [];
    for (const k of this.kf) if (k.modelRef && out.indexOf(k.modelRef) < 0) out.push(k.modelRef);
    return out;
  }

  /** Embedded blob for a ref, if the studio shipped one. */
  modelBlob(ref: string): { mime: string; data: string } | null {
    const b = this.modelBlobs[ref];
    return b ? { mime: b.mime, data: b.data } : null;
  }

  /** Sampled appearance at age (morph across keyframes; shape flips mid-segment). */
  sampleAt(age: number, i: number): { size: number; r: number; g: number; b: number; a: number; shape: string } {
    const [k, e, raw] = this.locate(age);
    const a: Keyframe = this.kf[k], b: Keyframe = this.kf[Math.min(k + 1, this.kf.length - 1)];
    const sMin: number = a.size + (b.size - a.size) * e;
    const sMax: number = a.sizeMax + (b.sizeMax - a.sizeMax) * e;
    return {
      size: Math.max(0.5, (sMin + (sMax - sMin) * this.sizeRatio[i]) * 0.5),
      r: Math.round(a.color.r + (b.color.r - a.color.r) * e),
      g: Math.round(a.color.g + (b.color.g - a.color.g) * e),
      b: Math.round(a.color.b + (b.color.b - a.color.b) * e),
      a: Math.max(0, Math.min(1, (a.opacity + (b.opacity - a.opacity) * e) / 255)),
      shape: raw >= 0.5 ? b.shape : a.shape,
    };
  }

  project(x: number, y: number, z: number, cx: number, cy: number, focal: number):
      [number, number, number, number] {
    const sy: number = Math.sin(this.cam.yaw), cy2: number = Math.cos(this.cam.yaw);
    const sp: number = Math.sin(this.cam.pitch), cp: number = Math.cos(this.cam.pitch);
    const x1: number = x * cy2 + z * sy;
    const z1: number = -x * sy + z * cy2;
    const y2: number = y * cp - z1 * sp;
    const z2: number = y * sp + z1 * cp;
    const s: number = this.cam.zoom * focal / (focal + z2);
    return [cx + x1 * s, cy - y2 * s, s, z2];
  }

  render(ctx: CanvasRenderingContext2D): void {
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (let i = 0; i < this.count; i++) {
      const s = this.sampleAt(this.age[i], i);
      this.traceShape(ctx, s.shape, this.px[i], this.py[i], s.size,
        `rgba(${s.r},${s.g},${s.b},${s.a.toFixed(3)})`,
        `rgba(${s.r},${s.g},${s.b},${(s.a * 0.35).toFixed(3)})`);
    }
    ctx.restore();
  }

  /** Full 3D scene: bg + floor grid + axes + projected particles. */
  renderScene(ctx: CanvasRenderingContext2D, W: number, H: number): void {
    ctx.fillStyle = "#14151c"; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#1e1f28";
    const s: number = 18;
    for (let y = 0; y < H; y += s)
      for (let x = ((y / s) % 2) * s; x < W; x += s * 2)
        ctx.fillRect(x, y, s, s);
    const cx: number = W / 2, cy: number = H * 0.52;
    const focal: number = (H * 0.5) / Math.tan(30 * Math.PI / 180);
    ctx.strokeStyle = "#2c2e44"; ctx.lineWidth = 1; ctx.beginPath();
    for (let k = -5; k <= 5; k++) {
      const d: number = k * 52;
      let a = this.project(-260, 0, d, cx, cy, focal);
      let b = this.project(260, 0, d, cx, cy, focal);
      ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      a = this.project(d, 0, -260, cx, cy, focal);
      b = this.project(d, 0, 260, cx, cy, focal);
      ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
    }
    ctx.stroke();
    const o = this.project(0, 0, 0, cx, cy, focal);
    const axes: Array<[number, number, number, string]> =
      [[70, 0, 0, "#ff3b3b"], [0, 70, 0, "#3ddc84"], [0, 0, 70, "#2f6bff"]];
    ctx.lineWidth = 3;
    for (const [ax, ay, az, col] of axes) {
      const t = this.project(ax, ay, az, cx, cy, focal);
      ctx.strokeStyle = col;
      ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(t[0], t[1]); ctx.stroke();
    }
    ctx.fillStyle = "#ffffff";
    ctx.beginPath(); ctx.arc(o[0], o[1], 6, 0, 6.2832); ctx.fill();
    ctx.save();
    ctx.globalCompositeOperation = "lighter"; // order-free blending, no sort needed
    for (let i = 0; i < this.count; i++) {
      const pr = this.project(this.px[i], this.py[i], this.pz[i], cx, cy, focal);
      const sm = this.sampleAt(this.age[i], i);
      this.traceShape(ctx, sm.shape, pr[0], pr[1], Math.max(1, sm.size * pr[2]),
        `rgba(${sm.r},${sm.g},${sm.b},${sm.a.toFixed(3)})`,
        `rgba(${sm.r},${sm.g},${sm.b},${(sm.a * 0.35).toFixed(3)})`);
    }
    ctx.restore();
  }

  /** Flat preview approximations of every supported shape (1-2 paths each). */
  traceShape(ctx: CanvasRenderingContext2D, shape: string, x: number, y: number,
    r: number, col: string, glow: string): void {
    const poly = (pts: number[]): void => {
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(x, y, r * 2.1, 0, 6.2832); ctx.fill();
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.moveTo(x + pts[0] * r, y + pts[1] * r);
      for (let k = 2; k < pts.length; k += 2) ctx.lineTo(x + pts[k] * r, y + pts[k + 1] * r);
      ctx.closePath(); ctx.fill();
    };
    switch (shape) {
      case "square": poly([-1, -1, 1, -1, 1, 1, -1, 1]); return;
      case "cube": poly([-0.9, -0.9, 0.9, -0.9, 0.9, 0.9, -0.9, 0.9]); return;
      case "billboard": poly([-1, -1, 1, -1, 1, 1, -1, 1]); return;
      case "triangle": poly([0, -1.2, 1.1, 0.9, -1.1, 0.9]); return;
      case "pyramid": poly([0, -1.2, 1.1, 0.8, -1.1, 0.8]); return;
      case "diamond": poly([0, -1, 0.7, 0, 0, 1, -0.7, 0]); return;
      case "star": {
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(x, y, r * 2.1, 0, 6.2832); ctx.fill();
        ctx.fillStyle = col;
        ctx.beginPath();
        for (let k = 0; k < 10; k++) {
          const a: number = (k / 10) * Math.PI * 2 - Math.PI / 2;
          const rr2: number = (k % 2 === 0) ? r : r * 0.45;
          const px2: number = x + Math.cos(a) * rr2, py2: number = y + Math.sin(a) * rr2;
          if (k === 0) ctx.moveTo(px2, py2); else ctx.lineTo(px2, py2);
        }
        ctx.closePath(); ctx.fill();
        return;
      }
      case "line":
        ctx.strokeStyle = col; ctx.lineWidth = Math.max(2, r * 0.5);
        ctx.beginPath(); ctx.moveTo(x - r * 1.6, y); ctx.lineTo(x + r * 1.6, y); ctx.stroke();
        return;
      case "torus":
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
        ctx.globalCompositeOperation = "destination-out";
        ctx.beginPath(); ctx.arc(x, y, r * 0.45, 0, 6.2832); ctx.fill();
        ctx.globalCompositeOperation = "lighter";
        return;
      case "custom":
        ctx.strokeStyle = col; ctx.lineWidth = 2;
        ctx.strokeRect(x - r, y - r, r * 2, r * 2);
        return;
      default: // sphere, circle + fallback
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(x, y, r * 2.1, 0, 6.2832); ctx.fill();
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
        return;
    }
  }
}
