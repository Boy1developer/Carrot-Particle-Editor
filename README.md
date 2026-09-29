# 🥕 Carrot Particle Editor

**Advanced Particle Emitter** — a 2D/3D particle system extension for [GDevelop](https://gdevelop.io), paired with **Carrot Particle Editor**, a standalone desktop tool for authoring particle effects visually with real-time GPU preview.

> Part of the **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** ecosystem. The "Advanced particle editor for stunning VFX" mentioned in the engine's feature list is this project.

<!-- TODO: add a screenshot or GIF of the editor here -->
<!-- ![Carrot Particle Editor](docs/screenshot.png) -->

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Download](#download)
- [Project structure](#project-structure)
- [Getting started (from source)](#getting-started-from-source)
- [Using effects in GDevelop](#using-effects-in-gdevelop)
- [Testing](#testing)
- [Shared contracts](#shared-contracts)
- [Roadmap](#roadmap)
- [Related projects](#related-projects)
- [Author](#author)
- [License](#license)

## Overview

This repository is a two-part toolkit:

1. **`AdvancedParticleEmitter.json`** — a GDevelop extension (namespace `AdvancedParticleEmitter`, author *Carrot Studio*) that renders particle effects inside GDevelop games: 2D via [PixiJS](https://pixijs.com), 3D via [Three.js](https://threejs.org), using a shared custom JSON effect format.
2. **Carrot Particle Editor** — a Python/Tkinter desktop application (packaged as `CarrotParticleEditor.exe`) for designing those effects with a live preview, then exporting them to the extension's JSON format.

Both parts share a single source of truth for particle behavior, shapes, and the export format — see [Shared contracts](#shared-contracts).

Built to plug into **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** (a 2D/3D engine built on GDevelop Core), but usable in any GDevelop-based project.

## Features

- **12 particle shapes** — circle, square, triangle, star, diamond, line, custom, sphere, cube, pyramid, torus, billboard — shared between the 2D and 3D renderers.
- **Dual simulation core** — a Python reference implementation plus an optional compiled C++ core (`particle_core`) for faster live preview, checked for numerical parity against Python (99/99 test cases passing).
- **In-editor GPU preview (Tk fallback edition)** — a minimal offscreen OpenGL 3.3 renderer built with raw `ctypes` (no PyOpenGL/numpy dependency), with dirty-region redraw for performance. Toggled with the 🎮 GPU button at the top-right of the viewport. The main Dear PyGui edition renders its viewport with drawlist primitives instead, so it has no such switch.
- **Browser preview** — a self-contained `live_effect.html` (zero network fetches) rendering the same effect live via Three.js (3D) / PixiJS (2D).
- **One-command rebuild pipeline** — compile check → C++ core build (if stale) → PyInstaller packaging → smoke test → Windows shortcut generation.
- **Compatible JSON export** — matches the extension's v1.0 effect format (hyphenated easing: `linear` / `ease-in` / `ease-out` / `ease-in-out`).

## Download

Prebuilt Windows executables are published on the **[Releases](https://github.com/Boy1developer/Carrot-Particle-Editor/releases)** page.
Download `CarrotParticleEditor.exe` and run it — no Python installation required.

## Project structure

```text
Carrot-Particle-Editor/
├── assets/                        # Icons and static resources
├── core/                          # Simulation core (Python + C++) and its tests
├── preview/                       # Browser preview (Three.js / PixiJS) and its tests
├── render/                        # OpenGL preview renderer and its tests
├── particle_studio.py             # Main editor application (Tkinter)
├── rebuild_app.py                 # One-command build pipeline
├── CarrotParticleEditor.spec      # PyInstaller spec
├── AdvancedParticleEmitter.json   # GDevelop extension
├── sample_effect.json             # Example effect
├── APP_STRUCTURE.md               # Detailed architecture notes
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
python rebuild_app.py
```

This runs the full pipeline: compiles and validates the app, rebuilds the C++ core if it's stale, packages the executable with PyInstaller, runs a smoke boot test, and regenerates the Windows shortcut.

### Run

```bash
# From source
python particle_studio.py

# Or the packaged build
dist/CarrotParticleEditor.exe
```

## Using effects in GDevelop

1. Design your effect in Carrot Particle Editor and export it as a `.json` file.
2. In GDevelop, import the `AdvancedParticleEmitter.json` extension into your project.
3. Add the emitter behavior/object to your scene and load the exported effect file.
4. Run the preview to see the effect in your game.

> The exact action/condition names depend on the extension version — see the extension's in-editor descriptions.

## Testing

| Test | Covers |
| --- | --- |
| `core/test_parity.py` | Python vs C++ simulation output — 99/99 passing |
| `core/test_behavior.py` | Simulation behavior and performance (~4 ms @ 2,000 particles) |
| `render/test_gl.py` | OpenGL context initialization |
| `render/test_clip.py` | GL projection matrix parity with the editor's own projection |
| `render/test_cost.py` | Render-cost profiling (identified `photo.configure` as the main bottleneck) |
| `preview/test_engine*.mjs`, `test_guides.mjs`, `test_server.py` | Browser preview engine, 2D/3D scene layers, and guide rendering |

## Shared contracts

A few conventions are kept identical across the Python app, the C++ core, and the browser preview, so effects look and behave the same everywhere:

- **Particle record layout** — `[x, y, vx, vy, age, c0, c1, s0, s1, life, z, vz, shape, tracks, dx, dy, dz, gx, gy, gz, sizeRatio, speedRatio]`
- **`SHAPE_ORDER`** — 12 shapes, shared Python ↔ C++ ↔ preview
- **Export format** — GDevelop extension v1.0 (`2d: needShape` / `3d: mesh swap`), hyphenated easing values
- **GL coordinates** — sizes are resolved once in the vertex shader; the editor's own projection matrix is numerically matched in tests

## Roadmap

- [ ] Evaluate integration with a dedicated C++ particle library (Effekseer or SPARK) as a complement to the current custom core
- [x] Add ready-made effect presets (fire, smoke, sparks, magic)
- [ ] Add CI to run the parity and behavior tests automatically
- [ ] Add screenshots/GIFs and a step-by-step GDevelop tutorial

## Related projects

- **[Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine)** — the 2D/3D game engine this extension is built for, extending GDevelop Core with Blueprint scripting, PBR materials, advanced animation, and this particle system among its VFX tools.

## Author

**Carrot Studio** — Mostafa Fathy Thabet ([@Boy1developer](https://github.com/Boy1developer)) — contributor to [Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine).

## License

This project is released under the [MIT License](LICENSE).

Note: [Carrots Engine](https://github.com/Carrotstudio0/Carrots-Game-Engine) itself is distributed under its own separate license; that does not affect the license of this repository.https://github.com/Carrotstudio0/Carrots-Game-Engine/blob/main/LICENSE.md)).
