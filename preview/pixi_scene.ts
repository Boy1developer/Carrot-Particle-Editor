/**
 * PixiJS WebGL layer for the ParticleFX fast preview (2D mode).
 * - Reuses the ParticleEngine simulation + keyframe morph sampling
 * - One shared sprite pool (4000) with baked-glow textures per shape,
 *   tinted per particle, additive blending — same look as the 2D canvas
 *   preview, GPU-batched
 */
import * as PIXI from "pixi.js";
import type { ParticleEngine } from "./preview.js";
import {
  TrailCfg, TrailPt, TrailKey, flooredWidth, lutColor, outerColor,
  coreColor, flickerFactor, strideIndices,
} from "./trails.js";

const POOL = 4000;
const TEX = 128;          // texture atlas cell (px)
const TEX_R = TEX * 0.26; // shape radius inside the cell (room for glow)
const TRAIL_CAP = 384;    // max ribbons drawn per frame
const TRAIL_ST = 17;      // stations per ribbon

type Ctx2D = CanvasRenderingContext2D;

function bake(draw: (g: Ctx2D, c: number, r: number) => void): PIXI.Texture {
  const c: HTMLCanvasElement = document.createElement("canvas");
  c.width = TEX; c.height = TEX;
  const g: Ctx2D | null = c.getContext("2d");
  if (!g) throw new Error("2d context unavailable");
  g.clearRect(0, 0, TEX, TEX);
  g.fillStyle = "#ffffff";
  g.strokeStyle = "#ffffff";
  g.lineWidth = Math.max(2, TEX * 0.03);
  g.shadowColor = "rgba(255,255,255,0.85)";
  g.shadowBlur = TEX * 0.10;
  draw(g, TEX / 2, TEX_R);
  return PIXI.Texture.from(c);
}

function starPath(g: Ctx2D, c: number, r: number): void {
  g.beginPath();
  for (let k = 0; k < 10; k++) {
    const a: number = (k / 10) * Math.PI * 2 - Math.PI / 2;
    const rr: number = (k % 2 === 0) ? r : r * 0.45;
    const x: number = c + Math.cos(a) * rr, y: number = c + Math.sin(a) * rr;
    if (k === 0) g.moveTo(x, y); else g.lineTo(x, y);
  }
  g.closePath(); g.fill();
}

function buildTextures(): Record<string, PIXI.Texture> {
  const circle = (g: Ctx2D, c: number, r: number): void => {
    g.beginPath(); g.arc(c, c, r, 0, 6.2832); g.fill();
  };
  return {
    sphere: bake(circle),
    circle: bake(circle),
    square: bake((g, c, r) => { g.fillRect(c - r, c - r, r * 2, r * 2); }),
    cube: bake((g, c, r) => { g.fillRect(c - r * 0.9, c - r * 0.9, r * 1.8, r * 1.8); }),
    billboard: bake((g, c, r) => { g.fillRect(c - r, c - r, r * 2, r * 2); }),
    triangle: bake((g, c, r) => {
      g.beginPath(); g.moveTo(c, c - r * 1.2);
      g.lineTo(c + r * 1.1, c + r * 0.9); g.lineTo(c - r * 1.1, c + r * 0.9);
      g.closePath(); g.fill();
    }),
    pyramid: bake((g, c, r) => {
      g.beginPath(); g.moveTo(c, c - r * 1.2);
      g.lineTo(c + r * 1.1, c + r * 0.8); g.lineTo(c - r * 1.1, c + r * 0.8);
      g.closePath(); g.fill();
    }),
    diamond: bake((g, c, r) => {
      g.beginPath(); g.moveTo(c, c - r); g.lineTo(c + r * 0.7, c);
      g.lineTo(c, c + r); g.lineTo(c - r * 0.7, c);
      g.closePath(); g.fill();
    }),
    star: bake(starPath),
    line: bake((g, c, r) => { g.fillRect(c - r * 1.6, c - r * 0.22, r * 3.2, r * 0.44); }),
    torus: bake((g, c, r) => {
      g.beginPath(); g.arc(c, c, r, 0, 6.2832); g.fill();
      g.save();
      g.globalCompositeOperation = "destination-out";
      g.shadowBlur = 0;
      g.beginPath(); g.arc(c, c, r * 0.45, 0, 6.2832); g.fill();
      g.restore();
    }),
    custom: bake((g, c, r) => { g.strokeRect(c - r, c - r, r * 2, r * 2); }),
  };
}

export class PixiScene {
  private app: PIXI.Application = new PIXI.Application();
  private layer!: PIXI.Container;
  private trails!: PIXI.Graphics;
  private gizmo!: PIXI.Graphics;
  private grid!: PIXI.Graphics;
  private pool: PIXI.Sprite[] = [];
  private tex: Record<string, PIXI.Texture> = {};
  private prevN = 0;
  private lastW = 0;
  private lastH = 0;
  private blend = "";
  ready = false;

  constructor(private canvas: HTMLCanvasElement, private engine: ParticleEngine) {}

  async init(): Promise<void> {
    await this.app.init({
      canvas: this.canvas,
      background: "#14151c",
      antialias: true,
    });
    this.tex = buildTextures();
    this.grid = new PIXI.Graphics();
    this.app.stage.addChild(this.grid);
    this.layer = new PIXI.Container();
    this.layer.blendMode = "add";
    this.app.stage.addChild(this.layer);
    for (let i = 0; i < POOL; i++) {
      const sp = new PIXI.Sprite(this.tex["circle"]);
      sp.anchor.set(0.5);
      sp.visible = false;
      this.layer.addChild(sp);
      this.pool.push(sp);
    }
    this.trails = new PIXI.Graphics();
    this.layer.addChild(this.trails);
    this.gizmo = new PIXI.Graphics();
    this.app.stage.addChild(this.gizmo);
    this.ready = true;
  }

  private normShape(shape: string): string {
    const s: string = String(shape ?? "circle").toLowerCase();
    return Object.prototype.hasOwnProperty.call(this.tex, s) ? s : "circle";
  }

  /** Pixi blend string for an effect mode (same fallbacks as the extension). */
  private pixiBlend(mode: string): string {
    switch (String(mode ?? "Normal")) {
      case "Additive": return "add";
      case "Multiply": return "multiply";
      case "Subtractive": return "erase";
      case "Screen": return "screen";
      case "Overlay": return "overlay";
      case "Lighten": return "normal";
      default: return "normal";
    }
  }

  private drawGrid(W: number, H: number): void {
    const g: PIXI.Graphics = this.grid;
    g.clear();
    const horizon: number = H * 0.42;
    g.strokeStyle = { width: 1, color: 0x3a3d55 };
    g.moveTo(0, horizon); g.lineTo(W, horizon);
    g.strokeStyle = { width: 1, color: 0x2c2e44 };
    for (let i = 1; i < 9; i++) {
      const y: number = horizon + (H - horizon) * Math.pow(i / 9, 1.6);
      g.moveTo(0, y); g.lineTo(W, y);
    }
    const ccx: number = W / 2;
    for (let i = -10; i <= 10; i++) {
      g.moveTo(ccx, horizon); g.lineTo(ccx + (i * W) / 14, H);
    }
    g.stroke();
  }

  /** One ribbon as flat quads (glow + outer + core per segment). */
  private drawRibbon(g: PIXI.Graphics, pts: TrailPt[],
    cfg: TrailCfg, wlut: number[],
    grad: Array<[number, number, number, number]>, now: number,
    key: TrailKey): void {
    const n: number = pts.length;
    const idx: number[] = strideIndices(n, TRAIL_ST - 1);
    const S: number = idx.length;
    if (S < 2) return;
    let acc = 0;
    const ks: string = String(key);
    for (let i = 0; i < ks.length; i++) acc += ks.charCodeAt(i);
    const fl: number = flickerFactor(now, cfg.flickerHz, cfg.flickerAmt,
      (acc % 1000) / 1000);
    // station frames (2D normals, head = newest = last point)
    const fx: number[] = [], fy: number[] = [];
    const nx: number[] = [], ny: number[] = [];
    const tw: number[] = [];
    const te: Array<[number, number, number]> = [];
    const tc: Array<[number, number, number]> = [];
    const ta: number[] = [];
    let lx = 1, ly = 0;
    for (let s = 0; s < S; s++) {
      const p: TrailPt = pts[idx[s]];
      const t: number = 1 - idx[s] / (n - 1);
      const p0: TrailPt = pts[idx[Math.max(0, s - 1)]];
      const p1: TrailPt = pts[idx[Math.min(S - 1, s + 1)]];
      let dx: number = p1.x - p0.x, dy: number = p1.y - p0.y;
      const dl: number = Math.hypot(dx, dy);
      if (dl > 1e-6) { lx = -dy / dl; ly = dx / dl; }
      const w: number = flooredWidth(t, cfg, wlut);
      const [r, gg, b, a] = lutColor(grad, t);
      fx.push(p.x); fy.push(p.y); nx.push(lx); ny.push(ly); tw.push(w);
      te.push(outerColor([r, gg, b], cfg.edgeColor, cfg.intensity));
      tc.push(coreColor([r, gg, b], cfg.coreColor, cfg.intensity));
      ta.push(Math.max(0, Math.min(1, (a / 255) * fl)));
    }
    const quad = (half: (s: number) => number,
      col: (s: number) => [number, number, number],
      alpha: (s: number) => number): void => {
      for (let s = 0; s < S - 1; s++) {
        const h0: number = half(s), h1: number = half(s + 1);
        const c0 = col(s), c1 = col(s + 1);
        const a0: number = alpha(s), a1: number = alpha(s + 1);
        if (Math.max(a0, a1) <= 0) continue;
        const am: number = (a0 + a1) / 2;
        const rm: number = Math.round((c0[0] + c1[0]) / 2);
        const gm: number = Math.round((c0[1] + c1[1]) / 2);
        const bm: number = Math.round((c0[2] + c1[2]) / 2);
        g.poly([
          fx[s] + nx[s] * h0, fy[s] + ny[s] * h0,
          fx[s] - nx[s] * h0, fy[s] - ny[s] * h0,
          fx[s + 1] - nx[s + 1] * h1, fy[s + 1] - ny[s + 1] * h1,
          fx[s + 1] + nx[s + 1] * h1, fy[s + 1] + ny[s + 1] * h1,
        ]).fill({ color: (rm << 16) | (gm << 8) | bm, alpha: am });
      }
    };
    const gw: number = Math.max(0, cfg.glowWidth);
    const ga: number = Math.max(0, Math.min(1, cfg.glowAlpha));
    if (gw > 0 && ga > 0) {
      quad((s) => tw[s] / 2 + gw,
        (s) => te[s],
        (s) => ta[s] * ga);
    }
    quad((s) => tw[s] / 2, (s) => te[s], (s) => ta[s]);
    const cw: number = Math.max(0, Math.min(1, cfg.coreWidth));
    if (cw > 0) {
      quad((s) => (tw[s] / 2) * cw, (s) => tc[s], (s) => ta[s]);
    }
  }

  /** Sync sprites from the engine state. Engine.update() is driven by the
   *  shared rAF loop in preview.html; Pixi auto-renders on its own ticker. */
  sync(ex: number, ey: number): void {
    if (!this.ready) return;
    const W: number = Math.max(1, Math.round(this.canvas.clientWidth || 1));
    const H: number = Math.max(1, Math.round(this.canvas.clientHeight || 1));
    if (W !== this.lastW || H !== this.lastH) {
      this.lastW = W; this.lastH = H;
      const dpr: number = Math.min(2, window.devicePixelRatio || 1);
      this.app.renderer.resolution = dpr;
      this.app.renderer.resize(W, H);
      this.drawGrid(W, H);
    }
    const n: number = Math.min(this.engine.activeCount, POOL);
    const wantBlend: string = this.pixiBlend(this.engine.blendingMode());
    if (wantBlend !== this.blend) {
      this.blend = wantBlend;
      this.layer.blendMode = wantBlend as PIXI.BLEND_MODES;
    }
    const hideDots: boolean = this.engine.trailsHideDots();
    // margin cull: fully off-screen sprites stay invisible (no fill cost)
    const M = 96;
    for (let i = 0; i < n; i++) {
      const sp: PIXI.Sprite = this.pool[i];
      if (hideDots) { sp.visible = false; continue; }
      const st = this.engine.particleState(i);
      if (st.x < -M || st.y < -M || st.x > W + M || st.y > H + M) {
        sp.visible = false;
        continue;
      }
      const sm = this.engine.sampleAt(st.age, i);
      sp.texture = this.tex[this.normShape(sm.shape)];
      sp.position.set(st.x, st.y);
      const s: number = Math.max(0.5, sm.size / TEX_R);
      sp.scale.set(s);
      sp.tint = (sm.r << 16) | (sm.g << 8) | sm.b;
      sp.alpha = sm.a;
      sp.visible = true;
    }
    for (let i = n; i < this.prevN; i++) this.pool[i].visible = false;
    this.prevN = n;
    // ribbons (cleared + redrawn every frame; hidden without a block)
    const gz0: PIXI.Graphics = this.trails;
    gz0.clear();
    const tf = this.engine.trailFrame();
    if (tf) {
      const list = tf.trails;
      const use: number = Math.min(list.length, TRAIL_CAP);
      for (let r = 0; r < use; r++) {
        const tr = list[r];
        this.drawRibbon(gz0, tr.pts, tf.cfg, tf.wlut, tf.grad,
          tf.now, tr.key);
      }
    }
    // emitter gizmo (X red / Y blue)
    const gz: PIXI.Graphics = this.gizmo;
    gz.clear();
    gz.rect(ex, ey - 2, 95, 4); gz.fill({ color: 0xff3b3b });
    gz.rect(ex - 2, ey - 95, 4, 95); gz.fill({ color: 0x2f6bff });
  }
}
