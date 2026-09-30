# -*- coding: utf-8 -*-
"""End-to-end preview-path profiler (Phase 1: measurement only).

Stages per frame at ~2,000 particles:
  1. sim-py   : SimEngine.step_py equilibrium step
  2. sim-cpp  : particle_core.Engine.step equilibrium step
  3. gl       : GLView.render (offscreen GL + readback to PPM bytes)
  4. dpg      : headless drawlist submission (N draw_circle + clear)
  5. tk-photo : legacy Tk PhotoImage.configure from PPM bytes (if available)

Usage:  python bench/bench_preview.py [--n 2000] [--reps 20]
Stages that need hardware (GL) or a display (Tk) report UNAVAILABLE
instead of failing. No optimization here — this file only measures.
"""
import argparse
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "editor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DT = 1.0 / 60.0


def stage_sim(n):
    import particle_studio as PS
    import studio_imgui as S
    states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
    tracks = S.SimEngine._build_tracks(states, "2d")
    em = PS.default_emitter("2d")
    em["mode"] = "Infinite"
    em["flow"] = 5000.0
    cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0,
           "ox": 0.0, "oy": 0.0, "focal": 620.0}
    out = {}
    try:  # python reference
        random.seed(1)
        eng = S.SimEngine()
        for _ in range(90):
            eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, DT, n)
        ts = []
        for _ in range(30):
            t0 = time.perf_counter()
            c = eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, DT, n)
            ts.append((time.perf_counter() - t0) * 1000.0)
        out["sim-py"] = (statistics.mean(ts), statistics.pstdev(ts), c)
    except Exception as e:  # noqa: BLE001
        out["sim-py"] = ("FAIL: " + str(e)[:100], 0.0, 0)
    try:  # C++ core
        import particle_core as CXX
        e2 = CXX.Engine()
        e2.set_seed(7)
        e2.configure(em, tracks, False)
        for _ in range(90):
            e2.step(DT, 400, 300, 0, 0, 0, 0, 0, 0, n,
                    0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
        ts = []
        for _ in range(60):
            t0 = time.perf_counter()
            o = e2.step(DT, 400, 300, 0, 0, 0, 0, 0, 0, n,
                        0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
            ts.append((time.perf_counter() - t0) * 1000.0)
        out["sim-cpp"] = (statistics.mean(ts), statistics.pstdev(ts), len(o["x"]))
    except Exception as e:  # noqa: BLE001
        out["sim-cpp"] = ("FAIL: " + str(e)[:100], 0.0, 0)
    return out


def stage_gl(n, reps):
    try:
        from render.gl_view import GLView, mat_ortho
    except Exception as e:  # noqa: BLE001
        return {"gl-render": ("UNAVAILABLE(import): " + str(e)[:80], 0.0, 0)}
    try:
        v = GLView()
        if not v.ok:
            return {"gl-render": ("UNAVAILABLE(no GL context)", 0.0, 0)}
        random.seed(3)
        W, H = 800, 600
        items = [(random.uniform(0, W), random.uniform(0, H), 0.0,
                  random.uniform(4, 12), random.random(),
                  random.random(), random.random(),
                  random.uniform(0.4, 1.0)) for _ in range(n)]
        buckets = {"circle": items[: n // 2], "star": items[n // 2:]}
        glow = items
        clip = mat_ortho(0, W, 0, H, -1000, 1000)
        v.render(buckets, glow, W, H, ortho=1, clip=clip, zoom=1.0,
                 focal=620.0, bg=(0.08, 0.08, 0.10), grid=())
        ts = []
        png = b""
        for _ in range(reps):
            t0 = time.perf_counter()
            png = v.render(buckets, glow, W, H, ortho=1, clip=clip, zoom=1.0,
                           focal=620.0, bg=(0.08, 0.08, 0.10), grid=())
            ts.append((time.perf_counter() - t0) * 1000.0)
        v.close()
        return {"gl-render": (statistics.mean(ts), statistics.pstdev(ts),
                              len(png))}
    except Exception as e:  # noqa: BLE001
        return {"gl-render": ("UNAVAILABLE: " + str(e)[:100], 0.0, 0)}


def stage_dpg(n, reps):
    try:
        import dearpygui.dearpygui as dpg
        dpg.create_context()
        with dpg.window(label="bench", width=820, height=600):
            dl = dpg.add_drawlist(width=800, height=536)
        random.seed(5)
        pts = [(random.uniform(0, 800), random.uniform(0, 536),
                random.uniform(2, 8)) for _ in range(n)]
        col = [255, 170, 0, 255]
        for _ in range(3):  # warmup
            dpg.delete_item(dl, children_only=True)
            for x, y, r in pts:
                dpg.draw_circle([x, y], r, color=[0, 0, 0, 0],
                                fill=col, parent=dl)
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            dpg.delete_item(dl, children_only=True)
            for x, y, r in pts:
                dpg.draw_circle([x, y], r, color=[0, 0, 0, 0],
                                fill=col, parent=dl)
            ts.append((time.perf_counter() - t0) * 1000.0)
        dpg.destroy_context()
        return {"dpg-drawlist": (statistics.mean(ts), statistics.pstdev(ts), n)}
    except Exception as e:  # noqa: BLE001
        try:
            import dearpygui.dearpygui as dpg
            dpg.destroy_context()
        except Exception:  # noqa: BLE001
            pass
        return {"dpg-drawlist": ("UNAVAILABLE: " + str(e)[:100], 0.0, 0)}


def stage_raster(n, reps):
    """Phase 3 path: GL small-frame render + PPM->floats + texture upload."""
    try:
        import particle_studio as PS
        import studio_imgui as S
        import raster_view as RV
        import dearpygui.dearpygui as dpg
        dpg.create_context()
        try:
            app = S.App()
            app.states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
            app.em = PS.default_emitter("2d")
            app.em["mode"] = "Infinite"
            app.em["flow"] = 5000.0
            app.em["maxParticles"] = n
            eff = app.current_effect()
            tracks = S.SimEngine._build_tracks(app.states, "2d")
            for _ in range(90):
                app.sim.step_cpp(eff, app.em, "2d", tracks, False, DT,
                                 400, 300, (0, 0, 0), app.cam, 620.0,
                                 400, 300, 0, 0, 0, n, ("bench", 0))
            out = app.sim._cpp_out
            cnt = len(out["x"])
            RV.frame_2d(app, out, 800, 536)
            ts = []
            for _ in range(reps):
                t0 = time.perf_counter()
                fr = RV.frame_2d(app, out, 800, 536)
                tag = RV.ensure_texture(fr[0], fr[1])
                RV.update_texture(fr[2])
                ts.append((time.perf_counter() - t0) * 1000.0)
            return {"raster-2d": (statistics.mean(ts), statistics.pstdev(ts), cnt)}
        finally:
            dpg.destroy_context()
            RV._tex_size = None
    except Exception as e:  # noqa: BLE001
        return {"raster-2d": ("UNAVAILABLE: " + str(e)[:100], 0.0, 0)}


def stage_tk_photo(png_bytes, reps):
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        ph = tk.PhotoImage()
        ph.configure(data=png_bytes, format="ppm")
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            ph.configure(data=png_bytes, format="ppm")
            ts.append((time.perf_counter() - t0) * 1000.0)
        root.destroy()
        return {"tk-photo": (statistics.mean(ts), statistics.pstdev(ts),
                             len(png_bytes))}
    except Exception as e:  # noqa: BLE001
        return {"tk-photo": ("UNAVAILABLE: " + str(e)[:100], 0.0, 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--reps", type=int, default=20)
    args = ap.parse_args()
    n = args.n

    print(f"# bench_preview @~{n} particles")
    stages = {}
    stages.update(stage_sim(n))
    stages.update(stage_gl(n, args.reps))
    stages.update(stage_dpg(n, args.reps))
    stages.update(stage_raster(n, args.reps))
    # legacy Tk handoff measured on a small frame (needs GL bytes first)
    png_small = b""
    try:
        from render.gl_view import GLView, mat_ortho
        _v = GLView()
        if _v.ok:
            png_small = _v.render(
                {"circle": [(400.0, 300.0, 0.0, 14.0, 1.0, 0.5, 0.0, 1.0)]},
                [(400.0, 300.0, 0.0, 14.0, 1.0, 0.5, 0.0, 1.0)],
                800, 600, ortho=1, clip=mat_ortho(0, 800, 0, 600, -1000, 1000),
                zoom=1.0, focal=620.0, bg=(0.08, 0.08, 0.10), grid=())
            _v.close()
    except Exception:  # noqa: BLE001
        pass
    if png_small:
        stages.update(stage_tk_photo(png_small, 6))
    else:
        stages["tk-photo"] = ("SKIPPED (no GL frame)", 0.0, 0)

    print(f"{'stage':>13} {'ms/frame':>10} {'stdev':>8} {'info':>12}")
    for k, (ms, sd, info) in stages.items():
        ms_s = f"{ms:>10.3f}" if isinstance(ms, float) else f"{str(ms):>10}"[:10]
        print(f"{k:>13} {ms_s} {sd:>8.3f} {info:>12}")


if __name__ == "__main__":
    main()
