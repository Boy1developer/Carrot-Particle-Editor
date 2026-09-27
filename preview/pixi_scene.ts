/**
 * PixiJS WebGL layer for the ParticleFX fast preview (2D mode).
 * - Reuses the ParticleEngine simulation + keyframe morph sampling
 * - One shared sprite pool (4000) with baked-glow textures per shape,
 *   tinted per particle, additive blending — same look as the 2D canvas
 *   preview, GPU-batched
 */
import * as PIXI from "pixi.js";
import type { ParticleEngine } from "./preview.js";

const POOL = 4000;
const TEX = 128;          // texture atlas cell (px)
const TEX_R = TEX * 0.26; // shape radius inside the cell (room for glow)

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
  private gizmo!: PIXI.Graphics;
  private grid!: PIXI.Graphics;
  private pool: PIXI.Sprite[] = [];
  private tex: Record<string, PIXI.Texture> = {};
  private prevN = 0;
  private lastW = 0;
  private lastH = 0;
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
    this.gizmo = new PIXI.Graphics();
    this.app.stage.addChild(this.gizmo);
    this.ready = true;
  }

  private normShape(shape: string): string {
    const s: string = String(shape ?? "circle").toLowerCase();
    return Object.prototype.hasOwnProperty.call(this.tex, s) ? s : "circle";
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
    for (let i = 0; i < n; i++) {
      const st = this.engine.particleState(i);
      const sm = this.engine.sampleAt(st.age, i);
      const sp: PIXI.Sprite = this.pool[i];
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
    // emitter gizmo (X red / Y blue)
    const gz: PIXI.Graphics = this.gizmo;
    gz.clear();
    gz.rect(ex, ey - 2, 95, 4); gz.fill({ color: 0xff3b3b });
    gz.rect(ex - 2, ey - 95, 4, 95); gz.fill({ color: 0x2f6bff });
  }
}
