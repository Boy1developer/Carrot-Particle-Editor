# 🥕 Carrot Particle Editor

**Advanced Particle Emitter** — a 2D/3D particle system extension for [GDevelop](https://gdevelop.io), paired with **Carrot Particle Editor**, a standalone desktop tool for authoring particle effects visually with real-time GPU preview.

> Part of the **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** ecosystem — the "Advanced particle editor for stunning VFX" referenced in the main engine's feature list is this project.

---

## Overview

This repository is a two-part toolkit:

1. **`AdvancedParticleEmitter.json`** — a GDevelop extension (namespace `AdvancedParticleEmitter`, author *Carrot Studio*) that renders particle effects inside GDevelop games: 2D via [PixiJS](https://pixijs.com), 3D via [Three.js](https://threejs.org), using a shared custom JSON effect format.
2. **Carrot Particle Editor** — a Python/Tkinter desktop application (packaged as `CarrotParticleEditor.exe`) for designing those effects with a live preview, before exporting them to the extension's JSON format.

The two share a single source of truth for particle behavior, shapes, and the export format — see [Shared contracts](#shared-contracts) below.

Built independently to plug into **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** — a open-source 2D/3D game engine built on GDevelop Core — but usable in any GDevelop-based project.

## Features

- **12 particle shapes** — circle, square, triangle, star, diamond, line, custom, sphere, cube, pyramid, torus, billboard — shared between the 2D and 3D renderers.
- **Dual simulation core** — a Python reference implementation plus an optional compiled C++ core (`particle_core`) for faster live preview, checked for numerical parity against Python (99/99 test cases passing).
- **In-editor GPU preview** — a minimal offscreen OpenGL 3.3 renderer built with raw `ctypes` (no PyOpenGL/numpy dependency), with dirty-region redraw for performance.
- **Browser preview** — a self-contained `live_effect.html` (zero network fetches) rendering the same effect live via Three.js (3D) / PixiJS (2D).
- **One-command rebuild pipeline** — compile check → C++ core build (if stale) → PyInstaller packaging → smoke test → Windows shortcut generation.
- **Compatible JSON export** — matches the extension's v1.0 effect format (hyphenated easing: `linear` / `ease-in` / `ease-out` / `ease-in-out`).

## Screenshots / Preview

<!-- TODO: add a screenshot or short GIF of the editor UI and the live GPU preview here.
     A visual tool like this benefits a lot from being shown, not just described. -->

## Project structure

```
studio_imgui.py                 # Desktop editor (Dear ImGui edition, drawlist viewport)
particle_studio.py              # Tk edition (fallback, shares the logic layer)
rebuild_app.py                  # One-command build pipeline
CarrotParticleEditor.spec       # PyInstaller spec (icon, datas, hidden imports)
AdvancedParticleEmitter.json    # GDevelop extension (2D/3D particle system)
sample_effect.json              # Example export
carrots-runtime/                # Typed TS loader for the effect JSON (Carrots Engine)
.gitignore / .gitattributes     # node_modules, dist, binaries out of git; generated preview excluded from stats

core/
├── particle_core.cpp           # C++ simulation core (mirrors Python logic)
├── build_core.py               # Builds particle_core.pyd (MSVC > g++ > clang++ > Zig)
├── test_parity.py              # C++ vs Python numerical parity
└── test_behavior.py            # Simulation behavior/perf tests

render/
├── gl_view.py                  # Offscreen GPU renderer (GLFW + raw OpenGL 3.3)
└── test_*.py                   # GL init, clip-matrix parity, render-cost tests

preview/
├── preview.ts / main.ts        # Browser preview engine + effect polling
├── three_scene.ts               # 3D scene layer (Three.js)
├── pixi_scene.ts                # 2D scene layer (PixiJS)
├── live_bundle.js               # esbuild bundle
├── live_effect.html             # Self-contained preview page
└── test_*.mjs / test_server.py  # Engine, scene, and guide tests

assets/                          # App/window icons
dist/CarrotParticleEditor.exe    # Packaged app (regenerated on every rebuild)
```

## Getting started

### Requirements

- Python 3.14
- `pip install dearpygui` — ImGui UI layer (`studio_imgui.py`)
- A C++ compiler for the optional simulation core: MSVC, g++, clang++, or Zig (auto-detected in that order)
- Node.js — for building the browser preview (`three`, `pixi.js`, `typescript`, `esbuild`)

### Build

```
python rebuild_app.py
```

This runs the full pipeline: compiles and validates the app, rebuilds the C++ core if it's stale, packages the executable with PyInstaller, runs a smoke boot test, and regenerates the Windows shortcut.

### Run

Launch via **Carrot Particle Editor.lnk**, or run `dist/CarrotParticleEditor.exe` directly.

## Testing

| Test | Covers |
| --- | --- |
| `core/test_parity.py` | Python vs C++ simulation output — 99/99 passing |
| `core/test_behavior.py` | Simulation behavior and performance (~4ms @ 2,000 particles) |
| `render/test_gl.py` | OpenGL context initialization |
| `render/test_clip.py` | GL projection matrix parity with the editor's own projection |
| `render/test_cost.py` | Render-cost profiling (identified `photo.configure` as the main bottleneck) |
| `preview/test_engine*.mjs`, `test_guides.mjs`, `test_server.py` | Browser preview engine, 2D/3D scene layers, and guide rendering |

## Carrots Engine integration

`carrots-runtime/` is the typed TypeScript ingestion path for the exported
effect JSON (v1.0) — Carrots GDJS runtime is TypeScript (PixiJS 2D / Three.js
3D, JSON-based particle resources since engine `1.0.3`).

```ts
import { loadCarrotEffectFromJsonText, normalizeEffect } from "@carrot-studio/particle-runtime";
const effect = loadCarrotEffectFromJsonText(await res.text());
const runtime = normalizeEffect(effect); // 2d: needShape / 3d: mesh swap
```

```bash
node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json --noEmit
node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json
node carrots-runtime/test_loader.mjs
```

Generated preview artefacts (`preview/live_bundle.js`, `preview/live_effect.html`,
compiled `preview/*.js`) are marked `linguist-generated` in `.gitattributes`
so GitHub stats reflect real source; `node_modules/`, `dist/` and binaries
stay out of git (see `.gitignore`).

## Shared contracts

A few conventions are kept identical across the Python app, the C++ core, and the browser preview, so effects look and behave the same everywhere:

- **Particle record layout** — `[x, y, vx, vy, age, c0, c1, s0, s1, life, z, vz, shape, tracks, dx, dy, dz, gx, gy, gz, sizeRatio, speedRatio]`
- **`SHAPE_ORDER`** (12 shapes, shared Python ↔ C++ ↔ preview)
- **Export format** — GDevelop extension v1.0 (`2d: needShape` / `3d: mesh swap`), hyphenated easing values
- **GL coordinates** — sizes are resolved once in the vertex shader; the editor's own projection matrix is numerically matched in tests

## Roadmap

- Evaluating integration with a dedicated C++ particle library (Effekseer or SPARK) as a possible complement to the current custom core.
- Additional particle shapes / emitter presets.
- Packaged builds for macOS/Linux in addition to the current Windows `.exe` pipeline.
- More export/import interoperability with other particle formats.

*(This list reflects current thinking — update it as priorities firm up.)*

## Related projects

- **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** — the 2D/3D game engine this extension is built for, extending GDevelop Core with Blueprint scripting, PBR materials, advanced animation, and this particle system among its VFX tools.

## Author

**Carrot Studio** — Mostafa Fathy Thabet ([@Boy1developer](https://github.com/Boy1developer)) — contributor to [Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine).

## License

This project (the GDevelop extension and the standalone Carrot Particle Editor) is released under the **MIT License** — see [LICENSE](LICENSE). This is independent of Carrots Engine's own proprietary license; only its GDevelop-derived core remains MIT (see its [LICENSE.md](https://github.com/Carrotstudio0/Carrots-Game-Engine/blob/main/LICENSE.md)).
