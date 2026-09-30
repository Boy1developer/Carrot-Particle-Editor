# Carrot Particle Editor — Upgrade PROGRESS

> Branch: `upgrade/master`. This file is the resume point: read it first, continue from the first unfinished phase.

## Final report (filled at the end of the whole run)
_Not yet — run in progress._

## Phase status
- [x] Phase 0: Repo hygiene — DONE (`phase-0-done`)
- [x] Phase 1: Benchmarks and profiling — DONE (`phase-1-done`)
- [ ] Phase 2: Single source of truth for contracts
- [ ] Phase 3: Viewport handoff (Dear PyGui)
- [ ] Phase 4: Simulation core performance
- [ ] Phase 5: Runtime rendering efficiency
- [ ] Phase 6: Blend modes (6a audit, 6b new modes, 6c per-emitter + parity)
- [ ] Phase 7: Effekseer-class features (1..7)
- [ ] Phase 8: Final quality gates

## Decisions made
- Phase 0: keep the legacy Tk code in `editor/particle_studio.py` untouched. Rationale: `editor/studio_imgui.py` (Dear PyGui) imports shared logic from it; deleting Tk risks breaking the app for zero hygiene gain. Hygiene scope = docs + ignore + CI only. (Conservative option per autonomy rule 6.)
- Phase 0: `preview/*.js` + `preview/live_bundle.js` + `preview/live_effect.html` stay tracked for now. Rationale: they are checked-in build outputs the exe + tests consume; untracking them mid-upgrade would break the build. Revisit in Phase 2/8 if a TS build step lands in CI.
- License = MIT (`LICENSE` file). `package.json` had no `license` field (shows as "none specified" on npm/GitHub) → set to `MIT` in both `package.json` files.
- Phase 1: benchmark metric uses actual mean stepped count (not the cap), because both cores apply 0.9–1.1 life jitter with independent RNG streams, so equilibrium counts differ slightly by design. No parity implication.

## Test results
- Phase 1 full run: ALL GREEN (parity 99/99, behavior, all headless UI, GL + clip + cost, preview server, all 7 Node preview tests, runtime loader).
- `py_compile` on editor/render/tools/core: OK. Extension JSON parses (v0.1.1, 2 objects).
- `core/test_parity.py`: 99/99. `core/test_behavior.py`: all invariants OK, C++ step 3.90ms @~2000 particles.
- Headless UI: build/logic/nav/color/mesh/morph/upload/blobs all OK.
- GL (run as `python -m render.test_*`; direct `python render/test_x.py` fails with ModuleNotFoundError — pre-existing, no bootstrap): GL_RENDER OK, clip 0/3000, cost raw 14ms / quantized 14ms.
- Preview server OK. Node preview tests all OK (engine/engine3d/guides/models/morph/bake/ext_bake).
- `tsc --noEmit` clean for `carrots-runtime/` and `preview/`; runtime loader test OK.
- REPAIRED in Phase 0: `preview/test_ext_bake.mjs` failed (`ext_bake_fn.js` missing — temp scan artifact deleted in an earlier commit). Fix: test now extracts `apfxBakeSkinned` source from `AdvancedParticleEmitter.json` at runtime. 1 attempt.
- `git ls-files` vs ignore patterns: no tracked build artifacts — `git rm --cached` not needed (the `build` substring hits are source files: `build_core.py`, `test_imgui_build.py`, `rebuild_app.py`).

## Benchmarks
- Baseline saved in `bench/BASELINE.md` (2026-09-30, DESKTOP-2O3SIPG, py3.14.3, C++ v1.0 MSVC/O2).
- Cores (particles/ms): 1k py 69.3 / c++ 410.1; 10k py 76.2 / c++ 251.3; 100k py 61.5 / c++ 208.5.
- Frame @2k (ms): sim-py 36.2, sim-cpp 7.1, gl-render+readback 11.8, dpg-drawlist 43.1, tk-photo 14.5.
- Frame reaches DPG as per-particle drawlist primitives — NO texture path exists; GL→PPM path is Tk/legacy + headless-tests only.
- C++ at 100k only ~3.5x Python: per-frame output marshaling (12 fresh lists + per-particle hex color parsing) dominates, not physics.

## Known limitations / unverified
- Anything only visible inside a running GDevelop game (extension 2D/3D runtime, blend modes, PixiJS version behavior) is unverified until tested in GDevelop.
- GL tests (`render/test_*.py`) need a GPU/GLFW context; may fail on headless CI — workflow runs them `continue-on-error`.
- `carrots-runtime/package.json` `build` script references `../../node_modules/typescript` which is wrong standalone (resolves above the repo); use repo-root `node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json` instead (CI does this). Left untouched in Phase 0.
- Preview Node tests print `MODULE_TYPELESS_PACKAGE_JSON` warnings (root `package.json` has no `"type"` field); harmless, left untouched.
