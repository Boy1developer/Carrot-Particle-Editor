# Carrot Particle Editor — Upgrade PROGRESS

> Branch: `upgrade/master`. This file is the resume point: read it first, continue from the first unfinished phase.

## Final report (filled at the end of the whole run)
_Not yet — run in progress._

## Phase status
- [x] Phase 0: Repo hygiene — DONE (`phase-0-done`)
- [x] Phase 1: Benchmarks and profiling — DONE (`phase-1-done`)
- [x] Phase 2: Single source of truth for contracts — DONE (`phase-2-done`)
- [x] Phase 3: Viewport handoff (Dear PyGui) — DONE (`phase-3-done`)
- [x] Phase 4: Simulation core performance — DONE (`phase-4-done`, 10x target MISSED — see below)
- [x] Phase 5: Runtime rendering efficiency — DONE (`phase-5-done`)
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
- Phase 2: Python + C++ import generated contracts directly; TypeScript sides and the extension are verify-only (their literals are regex-compared by `generate_contracts.py --check`). Rationale: `carrots-runtime` has `rootDir: src` (an outside import breaks `tsc`), preview `tsconfig.files` is brittle, and rewriting bundled extension JSON risks the game runtime. Revisit only if a TS build step lands in CI.
- Phase 2: schema validator is hand-rolled stdlib-only (type/required/enum/properties/items/minItems), unknown keys ignored for forward compatibility. No `jsonschema` dependency per the no-heavy-deps rule.
- Phase 2: migration is silent-heal + warnings (status line / debug log); only an explicitly newer `version` or a non-object raises.
- Phase 3: NO framework switch. DPG now has a real raster path (`editor/raster_view.py`: 320px GL render → one flat LUT comprehension → `add_raw_texture`/`set_value`, GPU-upscaled via `draw_image`); drawlist stays for <900 particles, custom meshes, and no-GL fallback.
- Phase 3: PBO async readback deliberately NOT implemented — synchronous readback at 320×214 is sub-ms inside a ~3ms GL stage; a PBO buffer lifecycle on the raw-ctypes path risks more than it saves. Revisit only if upload profiling says otherwise.
- Phase 3: dirty-region (`vp=` subrect) deliberately NOT used for the texture path — it would need a Python-side splice into a cached full frame every time the box moves; full small-frame render (~3ms GL) already bounds the cost. `vp=` stays available for the legacy Tk photo path.
- Phase 3: DPG raw-texture row 0 = top is assumed (matches the numerically verified PPM orientation: canvas-top dot → row 5/214); could not verify visually headless. If the raster image ever appears vertically flipped in-app, flip the row order in `ppm_to_floats`.

## Test results
- Phase 5 full run: ALL GREEN (parity 99/99, behavior, all headless UI incl. raster, GL + clip + cost, preview server, all 7 Node preview tests incl. recompiled scenes, runtime loader, contracts + `--check`, extension `node --check` via patch script).
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
- Phase 3 re-measure: raster-2d (GL 320px + LUT convert + texture upload) 26.1ms @~2k vs drawlist 43.2ms (1.65x on the draw stage; ~20fps → ~30fps frame with C++ sim). Drawlist scales ~22us/particle; raster is ~flat (26ms @2k, est. ~50ms @10k vs ~220ms vector ≈ 4.4x). Auto-switch threshold `MIN_N = 900` (crossover of measured curves; vector stays native-res sharp below it).
- Frame reaches DPG as per-particle drawlist primitives — NO texture path exists; GL→PPM path is Tk/legacy + headless-tests only.
- C++ at 100k only ~3.5x Python: per-frame output marshaling (12 fresh lists + per-particle hex color parsing) dominates, not physics.
- Phase 4 result: hoisted keyframe string work (color parse, easing enum, shape index) from per-particle to `configure()` — C++ @1k 2.36→0.87ms, @10k 38.5→18.5ms, @100k 452→140ms, behavior @2k ~4→1.45ms (≈2.8x). Parity 99/99 intact (values bit-identical by construction).
- Phase 4 10x target MISSED at 2k: floor analysis — each `step()` builds 12 fresh PyObjects/particle (~250ns) + 2 × `locate()` (old-age speed + new-age draw, both semantically required) + lerps/nearbyint (~450ns) ≈ 0.7us/particle ≈ 1.4ms @2k. 10x (0.2us) is unreachable without changing the 22-field dict-of-lists boundary. Rejected: backward output loop fusion (would reorder 2D stacking), output buffer reuse (saves only 12 list shells, not the 12n values; adds aliasing hazard), multithreading (GIL-bound output, overhead dominates ≤100k). PROPOSAL for later: boundary-v2 `advance()` + `fetch()` split or flat float buffers behind a format-version bump (needs Phase-2-style lockstep).
- Phase 4 pool/fixed-step status: particle SoA vectors already persist across frames (geometric growth, swap-remove kills — no per-frame particle allocation; only the boundary output lists allocate, as the contract requires). dt clamp [0, 0.05] is the existing fixed-step guard.
- Phase 5: browser preview was ALREADY batched (3D InstancedMesh ×12 shapes, 2D pooled sprites + baked shape textures). Added: reused instance counters + `visible=false` on empty buckets (3D), 96px-margin sprite cull (2D), `tools/build_preview.py` (tsc + esbuild bundle, bundle diff verified as one localized block).
- Phase 5: extension 3D pool was WRITE-ONLY (`getPooledParticle` had zero call sites) — spawns/flips now reuse pooled meshes (steady-state zero mesh/material churn), pool key includes blendingMode, flipped-away GLB meshes return to the pool (previously leaked). Per-frame THREE temps hoisted (billboard basis, alignToVelocity chain, color scratch). Via `tools/patch_perf.py` (anchored, idempotent) + `node --check`.
- Phase 5 deferred (conservative): extension InstancedMesh rewrite (one draw call/emitter) and 2D ParticleContainer (incompatible with Graphics children — needs baked-sprite approach + Pixi version audit from 6a). Both are unverifiable outside a running GDevelop game and risk the game runtime; revisit with GDevelop-side profiling.
- Phase 5 cache-key audit: geoCache=shape (blend-independent ✓), textureCache/modelCache=refId (cloned per use ✓), 3D pool=shape+ref+blend ✓ (fixed), 2D pool=shape+customId with per-frame `blendMode` set (✓ safe).

## Known limitations / unverified
- Anything only visible inside a running GDevelop game (extension 2D/3D runtime, blend modes, PixiJS version behavior) is unverified until tested in GDevelop. In particular Phase 5's extension pooling/temps patch is syntax-checked (`node --check`) and logic-reviewed but NOT run in GDevelop.
- Phase 3's DPG raster image orientation (row 0 = top) is assumed from the numerically verified PPM layout; flip rows in `ppm_to_floats` if the in-app image ever appears upside down.
- GL tests (`render/test_*.py`) need a GPU/GLFW context; may fail on headless CI — workflow runs them `continue-on-error`.
- `carrots-runtime/package.json` `build` script references `../../node_modules/typescript` which is wrong standalone (resolves above the repo); use repo-root `node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json` instead (CI does this). Left untouched in Phase 0.
- Preview Node tests print `MODULE_TYPELESS_PACKAGE_JSON` warnings (root `package.json` has no `"type"` field); harmless, left untouched.
