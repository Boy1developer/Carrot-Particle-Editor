<div align="center">

# 🥕 Carrot Particle Editor

**Design stunning 2D & 3D particle effects visually — and play them in GDevelop.**

A standalone desktop editor with real-time GPU preview, paired with the **Advanced Particle Emitter** extension for GDevelop.

[![Version](https://img.shields.io/badge/version-0.1.2-orange?style=for-the-badge)](https://github.com/Boy1developer/Carrot-Particle-Editor/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows)](https://github.com/Boy1developer/Carrot-Particle-Editor/releases)
[![GDevelop](https://img.shields.io/badge/GDevelop-extension-6c5ce7?style=for-the-badge)](https://gdevelop.io)

[**⬇️ Download**](https://github.com/Boy1developer/Carrot-Particle-Editor/releases) ·
[**✨ Features**](#-features) ·
[**🚀 Quick Start**](#-quick-start) ·
[**🎨 Blend Modes**](#-blend-modes) ·
[**🛣️ Roadmap**](#️-roadmap)

<br>

<img src="docs/screenshots/viewport-3d.png" alt="Carrot Particle Editor — 3D viewport" width="860">

</div>

---

## 📖 Overview

Carrot Particle Editor is a two-part toolkit:

| Part | What it is |
| --- | --- |
| **Carrot Particle Editor** | A Dear PyGui desktop app (`CarrotParticleEditor.exe`) for designing effects with a live viewport, then exporting them as JSON. |
| **Advanced Particle Emitter** | A GDevelop extension (`AdvancedParticleEmitter.json`) that renders those effects in-game: **2D** via [PixiJS](https://pixijs.com) and **3D** via [Three.js](https://threejs.org). |

Both parts share a single source of truth for particle behavior, shapes, and the export format (see [Shared contracts](#-shared-contracts)), so an effect looks the same in the editor, the browser preview, and your game.

> Part of the **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** ecosystem — the "Advanced particle editor for stunning VFX" in the engine's feature list is this project. It works in any GDevelop-based project.

---

## 🖼️ Screenshots

<table>
  <tr>
    <td align="center"><img src="docs/screenshots/viewport-3d.png" alt="3D viewport"><br><sub><b>3D viewport</b></sub></td>
    <td align="center"><img src="docs/screenshots/viewport-2d.png" alt="2D viewport"><br><sub><b>2D viewport</b></sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/fast-preview-3d.png" alt="3D fast preview"><br><sub><b>3D browser fast preview</b></sub></td>
    <td align="center"><img src="docs/screenshots/fast-preview-2d.png" alt="2D fast preview"><br><sub><b>2D browser fast preview</b></sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/emitter-panel.png" alt="Emitter panel"><br><sub><b>Emitter panel</b></sub></td>
    <td align="center"><img src="docs/screenshots/states-panel.png" alt="States panel"><br><sub><b>Per-state colors (3D)</b></sub></td>
  </tr>
</table>

<details>
<summary><b>More screenshots</b></summary>

<table>
  <tr>
    <td align="center"><img src="docs/screenshots/states-panel-2d.png" alt="States panel 2D"><br><sub>States panel (2D)</sub></td>
    <td align="center"><img src="docs/screenshots/custom-shape.png" alt="Custom shape"><br><sub>Custom shape</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/shapes-list-1.png" alt="3D shapes 1"><br><sub>3D shapes (1)</sub></td>
    <td align="center"><img src="docs/screenshots/shapes-list-2.png" alt="3D shapes 2"><br><sub>3D shapes (2)</sub></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="docs/screenshots/shapes-list-2d.png" alt="2D shapes"><br><sub>2D shapes</sub></td>
  </tr>
</table>

</details>

---

## ✨ Features

### 🎛️ Editor
- **12 particle shapes** — circle, square, triangle, star, diamond, line, custom, sphere, cube, pyramid, torus, billboard — shared by the 2D and 3D renderers.
- **Custom 3D models & images** — upload `.glb` / `.gltf` / `.obj` (or images for 2D). Models render as themselves in the viewport, the browser preview, and in-game. Rigged/skinned GLBs are baked to their rest pose automatically.
- **Per-state colors** — birth / mid / death each keep their own color. White means natural materials; any other color tints over the base.
- **Gradual shape morph** — birth-to-death shapes cross-fade around the mid-segment flip instead of snapping.
- **Ready-made templates** — Explosion, Fire, Rain, Snow.
- **Force fields** *(v1.1)* — age-phased turbulence, Y-axis vortex, linear-falloff attractor, and a bounce/friction collision plane. All off by default (legacy motion stays bit-identical).
- **Deterministic seed** — a nonzero `seed` replays the identical effect everywhere: editor (Python + C++), browser preview, and GDevelop runtime. `0` keeps legacy unseeded behavior.
- **Blend modes** — Normal, Additive, Subtractive, Multiply, Screen, Lighten, Overlay, selectable per emitter.

### ⚡ Performance
- **InstancedMesh batching** — ~580 draw calls collapse into ~12 buckets, verified **pixel-identical** per particle (matrix, color, alpha), including morph flips and all blend modes.
- **Lazy buckets** — created only for shapes in use; empty buckets cost zero draw calls.
- **Pooled runtime** — shape-aware mesh/material pooling, shared geometries, and no per-frame allocations in steady state. Automatic fallback to the classic path if instancing is unavailable.
- **Dual simulation core** — a Python reference plus an optional compiled **C++ core** for faster live preview, checked for numerical parity (99/99 cases) against Python.
- **Adaptive viewport** — crisp vector drawlist below ~900 particles; above that, the particle layer renders offscreen on the GPU and uploads as a texture.

### 🔍 Previews
- **In-editor GPU preview** — a minimal offscreen OpenGL 3.3 renderer built on raw `ctypes` (no PyOpenGL or numpy needed).
- **Browser fast preview** — a self-contained `live_effect.html` (zero network fetches) rendering the same effect live in Three.js (3D) / PixiJS (2D), with 500 ms live-sync.

---

## 🚀 Quick Start

### 1. Get the editor

Download `CarrotParticleEditor.exe` from the **[Releases](https://github.com/Boy1developer/Carrot-Particle-Editor/releases)** page and run it. No Python installation required.

**Requirements:** Windows 10/11 (64-bit) · GPU with OpenGL 3.3 support

<details>
<summary><b>Run from source / rebuild</b></summary>

```bash
pip install dearpygui
python editor/particle_studio.py
```

Rebuild the packaged app (compile check → C++ core build if stale → PyInstaller → smoke test → Windows shortcut):

```bash
python tools/rebuild_app.py
```

> Binaries (`dist/`, `*.exe`, `*.pyd`, `node_modules/`) are never committed. They are rebuilt locally and shipped through GitHub Releases.

</details>

### 2. Use effects in GDevelop

1. **Design** your effect in Carrot Particle Editor and export it as a `.json` file.
2. **Import** `AdvancedParticleEmitter.json` into your GDevelop project as an extension.
3. **Add** the emitter object to your scene and set its **ParticleJSON** resource to the exported file. If the effect uses a custom model, also set the **Models GLB** resource to your `.glb`.
4. **Run** the preview and enjoy your effect in-game.

> Exact action/condition names depend on the extension version — see the extension's in-editor descriptions.

---

## 🎨 Blend Modes

Set per emitter from the sidebar dropdown. At object level, `BlendingMode: 'JSON'` uses each emitter's own mode; any explicit value forces all emitters.

| Mode | 2D (PixiJS) | 3D (Three.js) | Desktop GL preview | Browser preview |
| --- | --- | --- | --- | --- |
| Normal | normal | normal | `SRC_ALPHA, ONE_MINUS_SRC_ALPHA` | normal |
| Additive | add | additive | `SRC_ALPHA, ONE` | add |
| Subtractive | erase ¹ | subtractive | reverse-subtract | erase ¹ |
| Multiply | multiply | multiply | `DST_COLOR, ONE_MINUS_SRC_ALPHA` | multiply |
| Screen | screen | custom (add + `ONE, ONE_MINUS_SRC_COLOR`) | `ONE, ONE_MINUS_SRC_COLOR` | screen |
| Lighten | → Normal ² | custom max-equation | max | → Normal ² |
| Overlay | overlay | → Normal ³ | → Normal ³ | overlay |

<sub>¹ Pixi core has no subtract · ² Pixi core has no lighten · ³ No fixed-function overlay</sub>

Unsupported combinations fall back to Normal with a **single** `console.warn` — never per frame, never throwing. Extension versions before 0.1.2 don't know Screen / Lighten / Overlay and render them as Normal.

---

## 🤝 Shared Contracts

Everything that must stay identical across Python, C++, the browser preview, and the GDevelop extension lives in one place: [`contracts/contracts.json`](contracts/contracts.json) — particle record layout, `SHAPE_ORDER`, easings, blend modes, export schema, and morph window.

[`tools/generate_contracts.py`](tools/generate_contracts.py) regenerates the language bindings in [`contracts/gen/`](contracts/gen/) (Python, C++ header, TypeScript reference, JSON Schema). **Edit the JSON, run the generator, never the outputs.** CI fails on stale files or drifted consumers.

- **Python** (`editor/particle_studio.py`) and the **C++ core** (`core/particle_core.cpp`) import the generated files directly.
- **TypeScript** (`preview/`, `carrots-runtime/`) and the **GDevelop extension** keep literal copies for bundling reasons; the check script verifies they match.

**Export format v1.1** — validated against `contracts/gen/schema.json` on save and load, with hyphenated easing values (`linear` / `ease-in` / `ease-out` / `ease-in-out`). `migrate_effect()` heals old files automatically (missing version, v1.0 → v1.1, camelCase easings, missing blend mode / seed).

**Particle record layout:**

```
[x, y, vx, vy, age, c0, c1, s0, s1, life, z, vz, shape, tracks,
 dx, dy, dz, gx, gy, gz, sizeRatio, speedRatio]
```

---

## 🧪 Testing

CI runs the parity, behavior, and contract checks on every push (`.github/workflows/ci.yml`).

> **Naming note:** the editor UI is built on Dear PyGui, which wraps Dear ImGui — that is why the UI test files are prefixed `test_imgui_`.

<details>
<summary><b>Full test matrix</b></summary>

| Test | Covers |
| --- | --- |
| `core/test_parity.py` | Python vs C++ simulation output — 99/99 passing |
| `core/test_behavior.py` | Simulation behavior, morph-window keys, performance (~2–3 ms @ 2,000 particles) |
| `tests/test_imgui_build.py` | UI builds without errors (blend dropdown, seed box, force-field widgets) |
| `tests/test_imgui_logic.py` | Headless simulation logic (C++ path) |
| `tests/test_imgui_nav.py` | Viewport navigation (WASD/arrows, Q/E, F, Shift×3) |
| `tests/test_imgui_color.py` | Per-state color persistence across birth/death switches |
| `tests/test_imgui_mesh.py` | Uploaded models render as meshes, tint, culling, LOD |
| `tests/test_imgui_morph.py` | Shape cross-fade window (edges, split alpha, legacy fallback) |
| `tests/test_imgui_upload.py` | Upload chain, OBJ parsing, big-JSON node names, bone-node fallback |
| `tests/test_imgui_raster.py` | Raster path: PPM conversion, GL orientation, auto-switch, no-GL fallback |
| `tests/test_preview_blobs.py` | Model-blob embedding for the browser preview |
| `tests/test_contracts.py` | Generated bindings = source, C++ order, schema accept/reject, migration |
| `tests/test_gl_blend.py` | Pixel-level GL formulas per blend mode + fallbacks |
| `tests/test_blend_modes.py` | Blend round-trip, sanitize, sample layers |
| `tests/test_seed.py` | Seed replay identical (Python + C++), divergence, seed-0 legacy |
| `tests/test_fields.py` | Field formulas, off-identical, perturb/replay, collision, attractor (Py + C++) |
| `preview/test_blend.mjs` | Extension blend mappings + resolution (stubbed runtimes) |
| `preview/test_seed.mjs` | Preview replay identical + extension RNG extraction |
| `preview/test_fields.mjs` | Extension helpers == Python + preview field behavior |
| `preview/test_ext_runtime.mjs` | Shipped 3D runtime headless (stub gdjs + real three.js) |
| `preview/test_engine.mjs`, `test_engine3d.mjs`, `test_guides.mjs`, `test_server.py` | Browser preview engine, 2D/3D scene layers, guides |
| `preview/test_models.mjs` | Model-blob caching and live-push behavior |
| `preview/test_morph.mjs` | Preview-side `morphAt()` cross-fade sampling |
| `preview/test_bake.mjs` / `test_ext_bake.mjs` | Skinned-mesh rest-pose baking (preview + shipped extension) |
| `tools/check_perf.py` | CI perf gate: C++ throughput floor |
| `render/test_gl.py`, `test_clip.py`, `test_cost.py` | GL context init, projection parity, render-cost profiling |

</details>

---

## 🛣️ Roadmap

**Done**
- [x] Ready-made effect templates (Explosion, Fire, Rain, Snow)
- [x] CI for parity and behavior tests
- [x] Screenshots and a step-by-step GDevelop guide
- [x] InstancedMesh batching, lazy buckets, sampling diet *(v0.1.2)*
- [x] Screen / Lighten / Overlay blend modes *(v0.1.2)*
- [x] Deterministic seed + force fields *(v0.1.2)*

**Planned**
- [ ] Trails / ribbons renderer
- [ ] Over-life Bézier curves and gradient editor
- [ ] Flipbook animation, UV scroll, soft particles
- [ ] Effect node tree with parent/child emitters and sub-emitters
- [ ] Timeline with scrubbing and a preset gallery
- [ ] Golden-image tests (editor render vs browser preview)

---

## 🔗 Related Projects

- **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** — the 2D/3D engine this extension is built for. It extends GDevelop Core with Blueprint scripting, PBR materials, advanced animation, and this particle system among its VFX tools.

## 👤 Author

**Carrot Studio** — Mostafa Fathy Thabet ([@Boy1developer](https://github.com/Boy1developer)) — contributor to Carrots Engine.

## 📦 Third-Party

| Library | License | Used for |
| --- | --- | --- |
| [Dear PyGui](https://github.com/hoffstadt/DearPyGui) | MIT | Desktop editor UI |
| [Three.js](https://threejs.org) | MIT | 3D rendering (browser preview + GDevelop extension) |
| [PixiJS](https://pixijs.com) | MIT | 2D rendering (browser preview + GDevelop extension) |

## 📄 License

Released under the [MIT License](LICENSE).

[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine) is distributed under [its own separate license](https://github.com/Carrotstudio0/Carrots-Game-Engine/blob/main/LICENSE.md), which does not affect the license of this repository.

<div align="center">

<br>

Made with 🥕 by **Carrot Studio** · If this helps your game, consider giving it a ⭐

</div>
