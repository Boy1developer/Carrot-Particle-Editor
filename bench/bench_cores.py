# -*- coding: utf-8 -*-
"""Reproducible simulation-core benchmark (Phase 1: measurement only).

Times equilibrium `step()` for the Python reference (`SimEngine.step_py`)
and the C++ core (`particle_core.Engine.step`) at 1k / 10k / 100k particles.

Usage:  python bench/bench_cores.py [--sizes 1000,10000] [--json out.json]
Output: table on stdout; machine/method notes for bench/BASELINE.md.

No optimization here — this file only measures.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "editor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import particle_studio as PS
import studio_imgui as S

try:
    import particle_core as CXX
    HAS_CXX = True
except Exception as e:  # noqa: BLE001 — report, don't crash the bench
    HAS_CXX = False
    CXX = None
    print("C++ core unavailable:", e)

DT = 1.0 / 60.0
DEFAULT_SIZES = (1000, 10000, 100000)
REPS_PY = {1000: 30, 10000: 5, 100000: 3}
REPS_CXX = {1000: 200, 10000: 50, 100000: 10}


def make_world(n):
    states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
    tracks = S.SimEngine._build_tracks(states, "2d")
    em = PS.default_emitter("2d")
    em["mode"] = "Infinite"
    em["flow"] = float(n) * 60.0  # one frame of flow fills n particles
    cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0,
           "ox": 0.0, "oy": 0.0, "focal": 620.0}
    return em, tracks, cam


def bench_py(n):
    em, tracks, cam = make_world(n)
    eng = S.SimEngine()
    eng.seed_sim(1234)  # instance RNG: comparable streams across runs
    warm = 60 if n <= 10000 else 10
    for _ in range(warm):
        eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, DT, n)
    reps = REPS_PY.get(n, 5)
    ts, counts = [], []
    for _ in range(reps):
        t0 = time.perf_counter()
        c = eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, DT, n)
        ts.append((time.perf_counter() - t0) * 1000.0)
        counts.append(c)
    assert counts[-1] > 0, counts
    return ts, counts


def bench_cxx(n):
    em, tracks, _cam = make_world(n)
    eng = CXX.Engine()
    eng.set_seed(1234)
    eng.configure(em, tracks, False)
    for _ in range(60):
        eng.step(DT, 400, 300, 0, 0, 0, 0, 0, 0, n,
                 0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
    reps = REPS_CXX.get(n, 10)
    ts, counts = [], []
    for _ in range(reps):
        t0 = time.perf_counter()
        out = eng.step(DT, 400, 300, 0, 0, 0, 0, 0, 0, n,
                       0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
        ts.append((time.perf_counter() - t0) * 1000.0)
        counts.append(len(out["x"]))
    assert counts[-1] > 0, counts
    return ts, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    rows = []
    for n in sizes:
        py_ts, py_counts = bench_py(n)
        py_ms = statistics.mean(py_ts)
        py_n = statistics.mean(py_counts)
        rows.append({"n": n, "impl": "python",
                     "mean_count": py_n,
                     "ms_mean": py_ms,
                     "ms_stdev": statistics.pstdev(py_ts),
                     "reps": len(py_ts),
                     "particles_per_ms": py_n / py_ms if py_ms > 0 else 0.0})
        if HAS_CXX:
            cxx_ts, cxx_counts = bench_cxx(n)
            cxx_ms = statistics.mean(cxx_ts)
            cxx_n = statistics.mean(cxx_counts)
            rows.append({"n": n, "impl": "c++",
                         "mean_count": cxx_n,
                         "ms_mean": cxx_ms,
                         "ms_stdev": statistics.pstdev(cxx_ts),
                         "reps": len(cxx_ts),
                         "particles_per_ms": cxx_n / cxx_ms if cxx_ms > 0 else 0.0})

    meta = {"machine": platform.node(), "os": platform.platform(),
            "cpu": platform.processor() or platform.machine(),
            "python": platform.python_version(),
            "cxx_version": getattr(CXX, "__version__", None) if HAS_CXX else None,
            "dt": DT}
    print(f"# bench_cores ({meta['machine']} | {meta['os']} | py {meta['python']})")
    print(f"{'n':>8} {'impl':>7} {'mean_cnt':>9} {'ms/frame':>10} {'stdev':>8} "
          f"{'particles/ms':>13} {'reps':>5}")
    for r in rows:
        print(f"{r['n']:>8} {r['impl']:>7} {r['mean_count']:>9.0f} "
              f"{r['ms_mean']:>10.3f} "
              f"{r['ms_stdev']:>8.3f} {r['particles_per_ms']:>13.1f} "
              f"{r['reps']:>5}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "rows": rows}, f, indent=2)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
