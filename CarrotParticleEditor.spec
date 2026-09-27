# -*- mode: python ; coding: utf-8 -*-
import os as _os

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


a = Analysis(
    ['particle_studio.py'],
    pathex=[],
    binaries=[],
    datas=[('preview', 'preview'), ('assets', 'assets'), ('render', 'render'), ('node_modules/three/build/three.module.js', 'node_modules/three/build'), ('node_modules/pixi.js/dist/pixi.mjs', 'node_modules/pixi.js/dist')] + _glfw_datas,
    hiddenimports=['particle_core', 'render.gl_view', 'glfw'],
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
    icon=['assets/app_icon.ico'],
)
