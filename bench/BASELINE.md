# Baseline benchmarks (Phase 1 — before any optimization)

Date: 2026-09-30. Machine: DESKTOP-2O3SIPG, Windows-10-10.0.19045-SP0,
Python 3.14.3, C++ core v1.0 (MSVC, `/O2`), Node v24.14.0.
Method: `python bench/bench_cores.py` (equilibrium `step()`, dt=1/60,
2-state default effect, Infinite mode, flow sized to fill the cap) and
`python bench/bench_preview.py --n 2000 --reps 20` (per-stage frame timings).

## Core throughput (equilibrium step)

| cap | impl | mean count | ms/frame (mean ± stdev) | particles/ms |
| --- | --- | --- | --- | --- |
| 1,000 | python | 965 | 13.927 ± 4.823 | 69.3 |
| 1,000 | c++ | 967 | 2.358 ± 0.658 | 410.1 |
| 10,000 | python | 10,000 | 131.274 ± 1.428 | 76.2 |
| 10,000 | c++ | 9,684 | 38.542 ± 18.093 | 251.3 |
| 100,000 | python | 100,000 | 1624.788 ± 131.281 | 61.5 |
| 100,000 | c++ | 94,151 | 451.652 ± 77.549 | 208.5 |

Notes:
- Counts differ slightly between impls at equilibrium because both apply a
  0.9–1.1 life jitter with independent RNG streams (by design); the metric
  uses the actual mean stepped count, so it stays honest.
- C++ is only ~3.5x Python at 100k (target for Phase 4 is ≥10x at 2k):
  the C++ `step()` builds 12 fresh Python lists per frame and parses every
  keyframe `#rrggbb` color string per particle per frame — marshaling, not
  physics, dominates at scale. The stdev spikes (18ms @10k, 78ms @100k)
  point at per-frame allocation.
- Python stdev spikes @1k (±4.8ms) are consistent with per-spawn
  `copy.deepcopy(tracks)` + GC pressure.

## Preview path per stage @~2,000 particles

| stage | ms/frame (mean ± stdev) | info |
| --- | --- | --- |
| sim-py (equilibrium step) | 36.218 ± 3.050 | 1,973 particles |
| sim-cpp (equilibrium step) | 7.108 ± 2.573 | 1,958 particles |
| gl-render (offscreen GL + readback to PPM) | 11.771 ± 1.334 | 1,440,015 bytes @800×600 |
| dpg-drawlist (clear + 2,000 `draw_circle`) | 43.140 ± 2.673 | headless, no viewport |
| tk-photo (legacy `PhotoImage.configure`) | 14.468 ± 5.347 | 800×600 PPM bytes |

## How the frame reaches Dear PyGui today

It does **not** go through pixels. The DPG viewport (`editor/studio_imgui.py`,
`vp_draw` drawlist, 800×536) draws every particle as vector primitives
(`dpg.draw_circle` / `draw_rectangle` / lines, plus mesh polylines for custom
models) issued from Python each frame. There is no `add_raw_texture` anywhere
in the app, no PBO, no shared GL context.

The `render/gl_view.py` offscreen-GL → PPM-bytes path is used only by the
legacy Tk prototype (`particle_studio.py` → `PhotoImage`) and by headless
tests. `render/test_cost.py`'s `photo.configure` bottleneck (14ms here,
matching the old 28ms-full/6ms-half finding) is therefore a Tk-only ceiling —
it never appears in the DPG frame.

## Conclusions for the next phases

1. The DPG frame ceiling is drawlist submission: 43ms @2k particles, ~6x the
   C++ sim cost. Phase 3 must add a raster path (`add_raw_texture` from a
   contiguous buffer) for large counts and keep the drawlist only for small
   counts — no framework switch.
2. Sim is second: Python 36ms vs C++ 7ms @2k. Phase 4 (SoA, pool, no per-frame
   alloc, no per-particle hex parsing) targets ≥10x over the C++ baseline
   (i.e. ≤0.7ms @2k) and stability at 100k in the core alone.
3. GL render+readback at 800×600 costs 11.8ms — relevant only if Phase 3
   routes the raster path through `gl_view`; budget ~12ms of the frame.
