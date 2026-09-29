# -*- coding: utf-8 -*-
"""Build the C++ simulation core (particle_core.pyd) with zero manual setup.

Compiler pick order: MSVC (cl) > g++ > clang++ > Zig (auto-installed via pip).
Output: particle_core.pyd at the repo root (imported by editor/ via bootstrap).
Usage: python core/build_core.py [--clean]
"""
import os
import shutil
import site
import subprocess
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "core", "particle_core.cpp")
OUT = os.path.join(ROOT, "particle_core.pyd")
INC = sysconfig.get_paths()["include"]
LIB = os.path.join(sys.base_prefix, "libs")
PYVER = f"python{sys.version_info.major}{sys.version_info.minor}"  # e.g. python314


def run(cmd, **kw):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def zig_exe():
    for base in (site.getusersitepackages(), *site.getsitepackages()):
        z = os.path.join(base, "ziglang", "zig.exe")
        if os.path.isfile(z):
            return z
    zw = shutil.which("zig")
    return zw


def pip_install_zig():
    run([sys.executable, "-m", "pip", "install", "ziglang", "--quiet"])
    return zig_exe()


def build_msvc():
    run(["cl", "/nologo", "/O2", "/std:c++20", "/EHsc", "/MD", "/LD",
         f"/I{INC}", SRC, f"/link", f"/LIBPATH:{LIB}",
         f"{PYVER}.lib", f"/OUT:{OUT}"])
    for ext in (".exp", ".lib", ".obj"):
        p = os.path.join(ROOT, "particle_core" + ext)
        if os.path.isfile(p):
            os.remove(p)


def build_gnu(cc):
    run([cc, "-shared", "-O2", "-std=c++20", "-DNDEBUG", f"-I{INC}",
         SRC, "-o", OUT, f"-L{LIB}", f"-l{PYVER}"])


def build_zig(zig):
    run([zig, "c++", "-target", "x86_64-windows-gnu", "-shared", "-O2",
         "-std=c++20", "-DNDEBUG", "-Wno-nullability-completeness",
         f"-I{INC}", SRC, "-o", OUT, f"-L{LIB}", f"-l{PYVER}"])


def main():
    if "--clean" in sys.argv and os.path.isfile(OUT):
        os.remove(OUT)
        print("removed", OUT)
    if not os.path.isfile(SRC):
        sys.exit("missing " + SRC)
    if shutil.which("cl"):
        try:
            build_msvc()
        except subprocess.CalledProcessError as e:
            sys.exit(f"cl build failed: {e}")
    elif shutil.which("g++") or shutil.which("clang++"):
        cc = "g++" if shutil.which("g++") else "clang++"
        try:
            build_gnu(cc)
        except subprocess.CalledProcessError as e:
            sys.exit(f"{cc} build failed: {e}")
    else:
        zig = zig_exe() or pip_install_zig()
        if not zig:
            sys.exit("no C++ compiler found (need cl/g++/clang++ or pip install ziglang)")
        try:
            build_zig(zig)
        except subprocess.CalledProcessError as e:
            sys.exit(f"zig build failed: {e}")
    # smoke test
    sys.path.insert(0, ROOT)
    import particle_core
    print("particle_core", particle_core.__version__, "OK;",
          "shapes:", len(particle_core.SHAPE_ORDER))
    e = particle_core.Engine()
    e.configure({"flow": 40, "maxParticles": 300, "mode": "Infinite",
                 "emissionZone": {"shape": "Circle"},
                 "propagationCone": {"direction": 0, "spread": 90}}, [], False)
    print("BUILD_OK ->", OUT)


if __name__ == "__main__":
    main()
