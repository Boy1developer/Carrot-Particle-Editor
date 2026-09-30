# CI performance gate (Phase 8): fails on LARGE core regressions only.
#
# Runs bench/bench_cores.py at 1k particles and asserts the C++ throughput
# stays above a generous floor. The floor (300 particles/ms) sits ~27% below
# the ORIGINAL pre-optimization baseline (410) and ~3.7x below current
# (~1100), so shared-runner noise cannot flake it, while a catastrophic
# regression (accidental O(n^2), lost Phase-4 gains compounded, debug
# build) fails loudly.
#
# Usage: python tools/check_perf.py [--floor 300]
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=300.0)
    ap.add_argument("--sizes", default="1000")
    args = ap.parse_args()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tmp = tf.name
    r = subprocess.run([sys.executable, "bench/bench_cores.py",
                        "--sizes", args.sizes, "--json", tmp],
                       capture_output=True, text=True, cwd=ROOT)
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print(r.stderr[-2000:] if r.stderr else "")
        sys.exit("PERF-GATE: benchmark failed to run")
    with open(tmp, encoding="utf-8") as f:
        data = json.load(f)
    os.unlink(tmp)
    fails = []
    for row in data["rows"]:
        if row["impl"] == "c++":
            ok = row["particles_per_ms"] >= args.floor
            print("c++ @%d: %.1f particles/ms (floor %.1f) %s"
                  % (row["n"], row["particles_per_ms"], args.floor,
                     "OK" if ok else "FAIL"))
            if not ok:
                fails.append(row)
    if fails:
        sys.exit("PERF-GATE FAILED: %d row(s) below floor" % len(fails))
    print("PERF-GATE OK")


if __name__ == "__main__":
    main()
