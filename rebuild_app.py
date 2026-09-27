# -*- coding: utf-8 -*-
"""One-command rebuild: every source change lands in the special-icon app.

Does: py_compile gate -> refresh C++ core if stale -> PyInstaller (spec has
icon + datas + hiddenimports) -> smoke-boot exe -> (re)create shortcut ->
cleanup. Usage: python rebuild_app.py
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(ROOT, "dist", "CarrotParticleEditor.exe")
LNK = os.path.join(ROOT, "Carrot Particle Editor.lnk")
ICO = os.path.join(ROOT, "assets", "app_icon.ico")
SPEC = os.path.join(ROOT, "CarrotParticleEditor.spec")


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def exe_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CarrotParticleEditor.exe", "/FO", "CSV"],
            capture_output=True, text=True, cwd=ROOT).stdout
        return "CarrotParticleEditor.exe" in out and out.count("\n") > 1
    except Exception:
        return False


def main():
    # 0) syntax gate
    run([sys.executable, "-m", "py_compile", "particle_studio.py"])
    # 1) refresh C++ core when its source is newer than the built .pyd
    src = os.path.join(ROOT, "core", "particle_core.cpp")
    pyd = os.path.join(ROOT, "particle_core.pyd")
    if os.path.isfile(src) and (not os.path.isfile(pyd)
                                or os.path.getmtime(src) > os.path.getmtime(pyd)):
        print("== C++ core stale -> rebuilding ==")
        run([sys.executable, "core/build_core.py"])
    # 2) refuse to build over a running app (Windows locks the file)
    if exe_running():
        sys.exit("ABORT: CarrotParticleEditor.exe is running - close it and rerun.")
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
          f"$sc.Description = 'Carrot Particle Editor'; $sc.Save()")
    run(["powershell", "-NoProfile", "-Command", ps])
    # 6) cleanup
    for d in ("build", "__pycache__"):
        p_ = os.path.join(ROOT, d)
        if os.path.isdir(p_):
            import shutil
            shutil.rmtree(p_, ignore_errors=True)
    print("REBUILD_OK: shortcut + exe carry every change with the special icon.")


if __name__ == "__main__":
    main()
