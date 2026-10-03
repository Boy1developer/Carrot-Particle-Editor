# -*- coding: utf-8 -*-
"""One-command rebuild: every source change lands in the special-icon app.

Does: py_compile gate -> refresh C++ core if stale -> PyInstaller (spec has
icon + datas + hiddenimports) -> smoke-boot exe -> (re)create shortcut ->
cleanup. Usage: python tools/rebuild_app.py (run from the repo root)
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "LempoParticleEditor.exe")
LNK = os.path.join(ROOT, "Lempo Particle Editor.lnk")
ICO = os.path.join(ROOT, "assets", "lempo.ico")
SPEC = os.path.join(ROOT, "packaging", "LempoParticleEditor.spec")


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def exe_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LempoParticleEditor.exe", "/FO", "CSV"],
            capture_output=True, text=True, cwd=ROOT).stdout
        return "LempoParticleEditor.exe" in out and out.count("\n") > 1
    except Exception:
        return False


def main():
    # 0) syntax gate (ImGui app + Tk fallback share the logic layer)
    run([sys.executable, "-m", "py_compile", "editor/studio_imgui.py"])
    run([sys.executable, "-m", "py_compile", "editor/particle_studio.py"])
    # 1) refresh C++ core when its sources are newer than the built .pyd
    srcs = [os.path.join(ROOT, "core", f)
            for f in os.listdir(os.path.join(ROOT, "core"))
            if f.endswith((".cpp", ".h"))]
    pyd = os.path.join(ROOT, "particle_core.pyd")
    if srcs and (not os.path.isfile(pyd) or max(
            os.path.getmtime(s) for s in srcs) > os.path.getmtime(pyd)):
        print("== C++ core stale -> rebuilding ==")
        run([sys.executable, "core/build_core.py"])
    # 2) refuse to build over a running app (Windows locks the file)
    if exe_running():
        sys.exit("ABORT: LempoParticleEditor.exe is running - close it and rerun.")
    # 3) build from spec (icon + datas + hiddenimports baked in)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", SPEC])
    if not os.path.isfile(EXE):
        sys.exit("ABORT: exe missing after build.")
    print(f"exe: {os.path.getsize(EXE) / 1e6:.1f} MB")
    # 4) smoke boot
    p = subprocess.Popen([EXE], cwd=ROOT)
    try:
        time.sleep(9)
        alive = p.poll() is None
        print("smoke boot alive after 9s:", alive)
        if not alive:
            sys.exit(f"ABORT: exe exited early with code {p.returncode}.")
    finally:
        if p.poll() is None:
            p.kill()
    # 5) shortcut with the special icon (recreated every time)
    ps = (f"$ws = New-Object -ComObject WScript.Shell; "
          f"$sc = $ws.CreateShortcut('{LNK}'); "
          f"$sc.TargetPath = '{EXE}'; $sc.WorkingDirectory = '{ROOT}'; "
          f"$sc.IconLocation = '{ICO}'; "
          f"$sc.Description = 'Lempo Particle Editor'; $sc.Save()")
    run(["powershell", "-NoProfile", "-Command", ps])
    # 6) nudge Explorer to drop its cached bitmaps so the shortcut (and
    #    the exe) show the fresh icon immediately (best-effort only)
    try:
        subprocess.run(["ie4uinit.exe", "-show"], cwd=ROOT,
                       capture_output=True, timeout=30)
    except Exception:
        pass
    # 7) cleanup
    for d in ("build", "__pycache__", "editor/__pycache__",
              "tools/__pycache__", "tests/__pycache__",
              "core/__pycache__", "render/__pycache__"):
        p_ = os.path.join(ROOT, d)
        if os.path.isdir(p_):
            import shutil
            shutil.rmtree(p_, ignore_errors=True)
    print("REBUILD_OK: shortcut + exe carry every change with the special icon.")


if __name__ == "__main__":
    main()
