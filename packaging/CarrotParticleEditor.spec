# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Carrot Particle Editor (Dear PyGui edition).
# Layout: this file lives in packaging/; every path below is anchored at
# the repo root so the build works no matter the invoking CWD.
# (PyInstaller execs the spec without __file__; it provides SPECPATH.)
import os as _os

_SPEC_DIR = SPECPATH  # directory containing this spec file
_ROOT = _os.path.dirname(_SPEC_DIR)

_glfw_datas = []
try:
    import glfw as _glfw_mod
    _gdir = _os.path.dirname(_glfw_mod.__file__)
    for _dll in ("glfw3.dll", "msvcr120.dll"):
        _p = _os.path.join(_gdir, _dll)
        if _os.path.isfile(_p):
            _glfw_datas.append((_p, "glfw"))
except Exception:
    pass


def _data(src, dst=None):
    return (_os.path.join(_ROOT, src), dst or src)


a = Analysis(
    [_os.path.join(_ROOT, 'editor', 'studio_imgui.py')],
    pathex=[_ROOT],
    binaries=[],
    datas=[_data('preview'), _data('assets'), _data('render'), _data('node_modules/three/build/three.module.js', 'node_modules/three/build'), _data('node_modules/pixi.js/dist/pixi.mjs', 'node_modules/pixi.js/dist')] + _glfw_datas,
    hiddenimports=['particle_core', 'render.gl_view', 'glfw', 'dearpygui',
                   'particle_studio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CarrotParticleEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[_os.path.join(_ROOT, 'assets', 'app_icon.ico')],
)
