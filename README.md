# 🥕 Carrot Particle Editor

**Advanced Particle Emitter** — a 2D/3D particle system extension for [GDevelop](https://gdevelop.io), paired with **Carrot Particle Editor**, a standalone desktop tool for authoring particle effects visually with real-time GPU preview.

> Part of the **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** ecosystem. The "Advanced particle editor for stunning VFX" mentioned in the engine's feature list is this project.

## Screenshots

| 3D viewport | 3D fast preview (three.js) |
| --- | --- |
| ![3D viewport](docs/screenshots/viewport-3d.png) | ![3D fast preview](docs/screenshots/fast-preview-3d.png) |

| 2D viewport | 2D fast preview (pixi.js) |
| --- | --- |
| ![2D viewport](docs/screenshots/viewport-2d.png) | ![2D fast preview](docs/screenshots/fast-preview-2d.png) |

| Emitter + propagation cone | States + templates (3D) | States + templates (2D) |
| --- | --- | --- |
| ![Emitter panel](docs/screenshots/emitter-panel.png) | ![States panel](docs/screenshots/states-panel.png) | ![States panel 2D](docs/screenshots/states-panel-2d.png) |

| 3D shape list | 2D shape list | Custom shape (uploaded 3D model) |
| --- | --- | --- |
| ![3D shapes 1](docs/screenshots/shapes-list-1.png) ![3D shapes 2](docs/screenshots/shapes-list-2.png) | ![2D shapes](docs/screenshots/shapes-list-2d.png) | ![Custom shape](docs/screenshots/custom-shape.png) |

---

## Table of contents

- [Overview](#overview)
- [Screenshots](#screenshots)
- [Features](#features)
- [Blend modes](#blend-modes)
- [Download](#download)
- [Project structure](#project-structure)
- [Getting started (from source)](#getting-started-from-source)
- [Using effects in GDevelop](#using-effects-in-gdevelop)
- [Testing](#testing)
- [Shared contracts](#shared-contracts)
- [Roadmap](#roadmap)
- [Related projects](#related-projects)
- [Author](#author)
- [Third-party](#third-party)
- [License](#license)

## Overview

This repository is a two-part toolkit:

1. **`AdvancedParticleEmitter.json`** — a GDevelop extension (namespace `AdvancedParticleEmitter`, author *Carrot Studio*) that renders particle effects inside GDevelop games: 2D via [PixiJS](https://pixijs.com), 3D via [Three.js](https://threejs.org), using a shared custom JSON effect format.
2. **Carrot Particle Editor** — a Dear PyGui desktop application (packaged as `CarrotParticleEditor.exe`) for designing those effects with a live viewport, then exporting them to the extension's JSON format.

Both parts share a single source of truth for particle behavior, shapes, and the export format — see [Shared contracts](#shared-contracts).

Built to plug into **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** (a 2D/3D engine built on GDevelop Core), but usable in any GDevelop-based project.

## Features

- **12 particle shapes** — circle, square, triangle, star, diamond, line, custom, sphere, cube, pyramid, torus, billboard — shared between the 2D and 3D renderers.
- **Custom 3D models & images** — upload `.glb` / `.gltf` / `.obj` models (or images for 2D); models render as themselves in the viewport, the browser preview, and export. The node picker lists only mesh-bearing nodes; picking a mesh-less (bone) node falls back to the whole file with a warning. Rigged/skinned GLBs are baked to their rest pose for preview and in-game.
- **Per-state colors** — each birth/mid/death state keeps its own color; white means natural materials, any other color tints over the base.
- **Gradual shape morph** — birth-to-death shapes cross-fade around the mid-segment flip instead of snapping (desktop viewport + browser preview; the game runtime keeps the classic flip).
- **Dual simulation core** — a Python reference implementation plus an optional compiled C++ core (`particle_core`) for faster live preview, checked for numerical parity against Python (99/99 test cases passing).
- **Deterministic seed** — a nonzero emitter `seed` replays the identical effect on every load in the editor (Python + C++), the browser preview, and the GDevelop runtime; `0` keeps legacy unseeded behavior.
- **Force fields** (v1.1) — optional emitter `fields`: age-phased turbulence, Y-axis vortex through the emitter point, linear-falloff attractor, and a bounce/friction collision plane; all off by default (legacy motion bit-identical).
- **Adaptive viewport** — crisp vector drawlist under ~900 particles; above that the particle layer renders offscreen (GL, 320px wide) and uploads as a raw texture while guides/gizmo stay vector. Custom meshes always use the vector path.
- **Pooled game runtime** — the GDevelop extension reuses meshes/materials from a shape-aware pool (no per-spawn GPU churn), shares geometries, and hoists per-frame temporaries; the browser preview renders 3D as instanced meshes and 2D as pooled tinted sprites.
- **In-editor GPU preview** — a minimal offscreen OpenGL 3.3 renderer built with raw `ctypes` (no PyOpenGL/numpy dependency), with dirty-region redraw for performance. Toggled with the 🎮 GPU button at the top-right of the viewport. The Dear PyGui viewport renders with drawlist primitives; the offscreen GL path is kept for headless verification and reference rendering.
- **Browser preview** — a self-contained `live_effect.html` (zero network fetches) rendering the same effect live via Three.js (3D) / PixiJS (2D).
- **One-command rebuild pipeline** — compile check → C++ core build (if stale) → PyInstaller packaging → smoke test → Windows shortcut generation.
- **Compatible JSON export** — matches the extension's v1.1 effect format (hyphenated easing: `linear` / `ease-in` / `ease-out` / `ease-in-out`); v1.0 files migrate automatically with defaults.

## Blend modes

Per-emitter `blendingMode` (sidebar dropdown; object-level `BlendingMode: 'JSON'` uses each emitter's own mode, any explicit value forces all emitters). Supported values and per-renderer behavior:

| Mode | 2D (PixiJS) | 3D (Three.js) | Desktop GL preview | Browser preview |
| --- | --- | --- | --- | --- |
| Normal | normal | normal | `SRC_ALPHA, ONE_MINUS_SRC_ALPHA` | normal |
| Additive | add | additive | `SRC_ALPHA, ONE` | add |
| Subtractive | erase (Pixi core has no subtract) | subtractive | reverse-subtract | erase |
| Multiply | multiply | multiply | `DST_COLOR, ONE_MINUS_SRC_ALPHA` | multiply |
| Screen | screen | custom (add + `ONE, ONE_MINUS_SRC_COLOR`) | `ONE, ONE_MINUS_SRC_COLOR` | screen |
| Lighten | → Normal (no core lighten) | custom max-equation | max | → normal |
| Overlay | overlay | → Normal (no fixed-function overlay) | → Normal | overlay |

Unsupported combinations fall back with a single `console.warn` (never per frame, never throwing). Note: extension versions before 0.1.2 don't know Screen/Lighten/Overlay and render them as Normal.

## Download

Prebuilt Windows executables are published on the **[Releases](https://github.com/Boy1developer/Carrot-Particle-Editor/releases)** page.
Download `CarrotParticleEditor.exe` and run it — no Python installation required.

> Binaries (`dist/`, `*.exe`, `*.pyd`, `node_modules/`) are never committed to the repo — they are rebuilt locally (`python tools/rebuild_app.py`) and shipped through GitHub Releases.

## Project structure

```text
Carrot-Particle-Editor/
├── .github/workflows/               # CI: compile + tests + contracts + perf gate
├── assets/                        # Icons and static resources
├── bench/                         # Reproducible benchmarks (bench_cores.py, bench_preview.py) + BASELINE.md
├── carrots-runtime/               # Game-runtime ingestion (normalizeEffect)
├── contracts/                     # Single source of truth (contracts.json + generated gen/)
├── core/                          # Simulation core (Python + C++) and its tests
├── docs/screenshots/              # README gallery images
├── editor/                        # Dear PyGui app (studio_imgui.py), raster viewport (raster_view.py), shared logic + legacy prototype (particle_studio.py), mesh_cache.py
├── packaging/                     # PyInstaller spec
├── preview/                       # Browser preview (Three.js / PixiJS) and its tests
├── render/                        # OpenGL preview renderer and its tests
├── tests/                         # Headless UI tests + contracts/seed/fields/blend/GL tests
├── tools/                         # Build pipeline (rebuild_app.py), contract generator, extension patch scripts, preview builder, perf gate
├── AdvancedParticleEmitter.json   # GDevelop extension (v0.1.2)
├── sample_effect.json             # Example effect (v1.1)
├── sample_blend_layers.json       # Additive/Normal/Screen sample effects (v1.1)
├── APP_STRUCTURE.md               # Detailed architecture notes
├── PROGRESS.md                    # Upgrade log: phases, decisions, benchmarks, limitations
├── package.json                   # Node dependencies for the browser preview
└── LICENSE                        # MIT
```

## Getting started (from source)

### Requirements

- Python 3.14
- A C++ compiler for the optional simulation core: MSVC, g++, clang++, or Zig (auto-detected in that order)
- Node.js — for building the browser preview (`three`, `pixi.js`, `typescript`, `esbuild`)

### Install

```bash
git clone https://github.com/Boy1developer/Carrot-Particle-Editor.git
cd Carrot-Particle-Editor
npm install
```

### Build

```bash
python tools/rebuild_app.py
```

This runs the full pipeline: compiles and validates the app, rebuilds the C++ core if it's stale, packages the executable with PyInstaller, runs a smoke boot test, and regenerates the Windows shortcut.

### Run

```bash
# From source (Dear PyGui edition; shared logic lives in editor/particle_studio.py)
python editor/studio_imgui.py

# Or the packaged build
dist/CarrotParticleEditor.exe
```

## Using effects in GDevelop

1. Design your effect in Carrot Particle Editor and export it as a `.json` file.
2. In GDevelop, import the `AdvancedParticleEmitter.json` extension into your project.
3. Add the emitter behavior/object to your scene, set its **ParticleJSON** resource to the exported file (and its **Models GLB** resource to the `.glb` if the effect uses a custom model).
4. Run the preview to see the effect in your game.

> The exact action/condition names depend on the extension version — see the extension's in-editor descriptions.

## Testing

| Test | Covers |
| --- | --- |
| `core/test_parity.py` | Python vs C++ simulation output — 99/99 passing |
| `core/test_behavior.py` | Simulation behavior, morph-window keys, and performance (~2–3 ms @ 2,000 particles) |
| `tests/test_imgui_build.py` | UI builds without errors (incl. blend dropdown, seed box, force-field widgets) |
| `tests/test_imgui_logic.py` | Headless simulation logic (C++ path) |
| `tests/test_imgui_nav.py` | Viewport navigation (WASD/arrows, Q/E, F, Shift×3) |
| `tests/test_imgui_color.py` | Per-state color persistence across birth/death switches |
| `tests/test_imgui_mesh.py` | Uploaded models render as meshes (not placeholders), tint, culling, LOD |
| `tests/test_imgui_morph.py` | Shape cross-fade window (edges, split alpha, legacy fallback) |
| `tests/test_imgui_upload.py` | Upload chain, OBJ parsing, big-JSON node names, bone-node fallback |
| `tests/test_imgui_raster.py` | Raster path: PPM conversion, GL orientation, auto-switch, no-GL fallback |
| `tests/test_preview_blobs.py` | Model-blob embedding for the browser preview |
| `tests/test_contracts.py` | Generated bindings = source, C++ order, schema accept/reject, migration |
| `tests/test_gl_blend.py` | Pixel-level GL formulas per blend mode + fallbacks |
| `tests/test_blend_modes.py` | Blend round-trip, sanitize, sample layers |
| `preview/test_blend.mjs` | Extension blend mappings + resolution (stubbed runtimes) |
| `tests/test_seed.py` | Seed replay identical (Python + C++), divergence, seed-0 legacy |
| `preview/test_seed.mjs` | Preview replay identical + extension RNG extraction |
| `tests/test_fields.py` | Field formulas, off-identical, perturb/replay, collision, attractor (Py + C++) |
| `preview/test_fields.mjs` | Extension helpers == Python + preview field behavior |
| `preview/test_ext_runtime.mjs` | Shipped 3D runtime headless (stub gdjs + real three.js): init, frames, replay, editor preview, fallbacks |
| `tools/check_perf.py` | CI perf gate: C++ throughput floor (fails on large regressions) |
| `render/test_gl.py` | OpenGL context initialization |
| `render/test_clip.py` | GL projection matrix parity with the editor's own projection |
| `render/test_cost.py` | Render-cost profiling (identified `photo.configure` as the main bottleneck) |
| `preview/test_engine.mjs`, `test_engine3d.mjs`, `test_guides.mjs`, `test_server.py` | Browser preview engine, 2D/3D scene layers, and guide rendering |
| `preview/test_models.mjs` | Model-blob caching and live-push behavior |
| `preview/test_morph.mjs` | Preview-side `morphAt()` cross-fade sampling |
| `preview/test_bake.mjs` | Skinned-mesh rest-pose baking (synthetic 2-bone rig) |
| `preview/test_ext_bake.mjs` | Extension's shipped bake function, extracted from the JSON at runtime |

## Shared contracts

Single source of truth: [`contracts/contracts.json`](contracts/contracts.json) (particle record layout, `SHAPE_ORDER`, easings, blend modes, export schema, morph window).
[`tools/generate_contracts.py`](tools/generate_contracts.py) regenerates the language bindings in [`contracts/gen/`](contracts/gen/) (Python, C++ header, TypeScript reference, export JSON Schema) — edit the JSON, run the generator, never the outputs. CI (`generate_contracts.py --check` + `tests/test_contracts.py`) fails on stale files or drifted consumers.

Wiring: Python (`editor/particle_studio.py`) and the C++ core (`core/particle_core.cpp`) import the generated files directly.
The TypeScript sides (`preview/`, `carrots-runtime/`) and the GDevelop extension keep their own literal copies for build/bundling reasons (`rootDir`, bundled JSON) — the check script verifies those literals match instead of rewriting them.

A few conventions are kept identical across the Python app, the C++ core, and the browser preview, so effects look and behave the same everywhere:

- **Particle record layout** — `[x, y, vx, vy, age, c0, c1, s0, s1, life, z, vz, shape, tracks, dx, dy, dz, gx, gy, gz, sizeRatio, speedRatio]`
- **`SHAPE_ORDER`** — 12 shapes, shared Python ↔ C++ ↔ preview
- **Export format** — GDevelop extension v1.1 (`2d: needShape` / `3d: mesh swap`), hyphenated easing values; validated against `contracts/gen/schema.json` on save and load, with `migrate_effect()` healing old files (missing version, v1.0→1.1 upgrade, camelCase easings, missing blend mode/seed)
- **GL coordinates** — sizes are resolved once in the vertex shader; the editor's own projection matrix is numerically matched in tests

## Roadmap

- [ ] Evaluate integration with a dedicated C++ particle library (Effekseer or SPARK) as a complement to the current custom core
- [x] Add ready-made effect presets (fire, smoke, sparks, magic)
- [x] Add CI to run the parity and behavior tests automatically (`.github/workflows/ci.yml`)
- [x] Add screenshots/GIFs and a step-by-step GDevelop tutorial
- [ ] Trails/ribbons renderer
- [ ] Over-life Bezier curves and gradient editor
- [ ] Flipbook animation, UV scroll, soft particles
- [ ] Effect node tree with parent/child emitters and sub-emitters
- [ ] Timeline with scrubbing and a preset gallery
- [ ] Golden-image tests (editor render vs browser preview)

## Related projects

- **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** — the 2D/3D game engine this extension is built for, extending GDevelop Core with Blueprint scripting, PBR materials, advanced animation, and this particle system among its VFX tools.

## Author

**Carrot Studio** — Mostafa Fathy Thabet ([@Boy1developer](https://github.com/Boy1developer)) — contributor to [Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine).

## Third-party

- [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (MIT) — the desktop editor UI.
- [Three.js](https://threejs.org) (MIT) — 3D rendering in the browser preview and the GDevelop extension.
- [PixiJS](https://pixijs.com) (MIT) — 2D rendering in the browser preview and the GDevelop extension.

## License

This project is released under the [MIT License](LICENSE).

Note: [Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine) itself is distributed under [its own separate license](https://github.com/Carrotstudio0/Carrots-Game-Engine/blob/main/LICENSE.md); that does not affect the license of this repository.
