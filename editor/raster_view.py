# -*- coding: utf-8 -*-
"""Raster viewport path for the Dear PyGui editor (Phase 3).

The DPG viewport draws every particle as vector primitives today (~21us
per dot — the frame ceiling at large counts). This module renders the
particle layer offscreen with the shared GL renderer at a small fixed
size, converts the PPM bytes to a float RGB buffer with ONE flat
comprehension over a precomputed 0..1 LUT (no per-pixel Python logic),
and uploads it via dpg.add_raw_texture / set_value. DPG upscales the
image to the full viewport on the GPU.

Guides (zone/cone), gizmo, vignette and text stay as drawlist overlays —
see paint_*() in studio_imgui.py. Custom meshes are NOT rasterized (GL
draws points for them), so the auto-switch stays on the vector path
whenever a custom model is in use.
"""
import os
import sys
import time

RW = 320  # raster width; height follows the viewport aspect
MIN_N = 900  # auto-switch threshold (tuned from bench, see PROGRESS.md)
TEX_TAG = "vp_raster_tex"
REG_TAG = "vp_raster_reg"

_LUT = [i / 255.0 for i in range(256)]

_gl = None
_gl_retry_t = 0.0
_tex_size = None


def raster_size(W, H):
    """Small size preserving the viewport aspect (matches draw_image upscale)."""
    rh = max(64, round(RW * max(1, H) / max(1, W)))
    return RW, rh


def ppm_to_floats(ppm):
    """PPM (P6, row 0 = top) -> (w, h, [r,g,b,...] floats 0..1).

    Single flat comprehension over the byte buffer — no per-pixel
    branching, no Python-level pixel loop, no intermediate lists.
    """
    head_end = ppm.index(b"\n255\n") + 5
    dims = ppm[:head_end].split()
    w, h = int(dims[1]), int(dims[2])
    raw = ppm[head_end:]
    L = _LUT
    return w, h, [L[b] for b in raw]


def has_dpg():
    try:
        import dearpygui.dearpygui  # noqa: F401
        return True
    except Exception:
        return False


def ensure_texture(w, h):
    """Create (or recreate on size change) the raw RGB texture. Tag or ""."""
    global _tex_size
    try:
        import dearpygui.dearpygui as dpg
        if _tex_size != (w, h) or not dpg.does_item_exist(TEX_TAG):
            if dpg.does_item_exist(REG_TAG):
                dpg.delete_item(REG_TAG)
            with dpg.texture_registry(tag=REG_TAG):
                dpg.add_raw_texture(w, h, [0.0] * (w * h * 3),
                                    format=dpg.mvFormat_Float_rgb, tag=TEX_TAG)
            _tex_size = (w, h)
        return TEX_TAG
    except Exception:
        return ""


def update_texture(floats):
    try:
        import dearpygui.dearpygui as dpg
        dpg.set_value(TEX_TAG, floats)
        return True
    except Exception:
        return False


def get_gl():
    """Lazy shared offscreen GL renderer (None when unavailable)."""
    global _gl, _gl_retry_t
    if _gl is not None:
        return _gl if getattr(_gl, "ok", False) else None
    try:
        from render.gl_view import GLView
    except Exception:
        return None
    if time.time() < _gl_retry_t:
        return None
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and "PYGLFW_LIBRARY" not in os.environ:
            cand = os.path.join(meipass, "glfw", "glfw3.dll")
            if os.path.isfile(cand):
                os.environ["PYGLFW_LIBRARY"] = cand
        gl = GLView()
        if getattr(gl, "ok", False):
            _gl = gl
            return gl
    except Exception:
        pass
    _gl = None
    _gl_retry_t = time.time() + 2.0
    return None


def has_custom_mesh(app):
    try:
        for s in (app.states or []):
            cm = s.get("customModel") or {}
            if cm.get("file"):
                return True
    except Exception:
        pass
    return False


def should_raster(app, n):
    """Auto-switch: big counts, C++ screen-space output, GL ready, no meshes."""
    try:
        if n < MIN_N:
            return False
        if has_custom_mesh(app):
            return False
        if getattr(app.sim, "_cpp_out", None) is None:
            return False
        return get_gl() is not None
    except Exception:
        return False


def _scale_split(PS, out, k, ox=0.0, oy=0.0, zoom=1.0, pivx=0.0, pivy=0.0):
    """_gl_split() buckets/glow mapped to raster-screen coords.

    out x/y are 2D WORLD coords: screen = pivot + offset + world * zoom,
    then downscaled by k (world z and colors pass through).
    """
    buckets, glow = PS.StudioApp._gl_split(out)
    ax, ay = pivx + ox, pivy + oy

    def _map(items):
        return [((ax + x * zoom) * k, (ay + y * zoom) * k, z,
                 max(1.0, r * zoom) * k, cr, cg, cb, a)
                for (x, y, z, r, cr, cg, cb, a) in items]

    sb = {}
    for shape, items in buckets.items():
        sb[shape] = _map(items)
    return sb, _map(glow)


def _zoom_grid_2d(PS, W, H, gx, horizon, zoom):
    """Vector grid (screen px) with the fan density following the zoom."""
    grid = PS.StudioApp._gl_grid_2d(None, W, H, gx, horizon)
    if not zoom or abs(zoom - 1.0) < 1e-9:
        return grid
    out = []
    for segs, col in grid:
        pts = list(segs)
        if pts and abs(pts[0] - gx) < 1e-9:
            # fan lines emanate from (gx, horizon): rescale the spread
            res = []
            for i in range(0, len(pts), 3):
                x, y, zz = pts[i], pts[i + 1], pts[i + 2]
                res += [gx + (x - gx) * zoom, y, zz]
            pts = res
        out.append((pts, col))
    return out


def frame_2d(app, out, W, H):
    """Render the 2D particle layer small. Returns (w, h, floats) or None."""
    import particle_studio as PS
    gl = get_gl()
    if gl is None or out is None or not len(out["x"]):
        return None
    try:
        from render.gl_view import mat_ortho as _ortho
        rw, rh = raster_size(W, H)
        k = rw / max(1.0, float(W))
        try:
            ox, oy, zoom = (app.cam["ox"], app.cam["oy"],
                            app.cam["zoom"])
        except Exception:
            ox, oy, zoom = 0.0, 0.0, 1.0
        buckets, glow = _scale_split(PS, out, k, ox, oy, zoom,
                                     W * 0.5, H * 0.52)
        try:
            glow_on = bool(app.glow)
        except Exception:
            glow_on = True
        if not (glow_on and len(out["x"]) <= 450):
            glow = []
        gx = (W * 0.5 + ox) * k
        horizon = (H * 0.42 + oy) * k
        grid = _zoom_grid_2d(
            PS, rw, rh, gx, horizon, zoom)
        bm = app.em.get("blendingMode") if isinstance(getattr(app, "em", None), dict) else None
        ppm = gl.render(buckets, glow, rw, rh, ortho=1,
                        clip=_ortho(0, rw, 0, rh, -1000, 1000),
                        zoom=1.0, focal=620.0,
                        bg=(22 / 255, 23 / 255, 31 / 255), grid=grid,
                        blend=bm if bm in PS.BLEND_MODES else "Normal")
        return ppm_to_floats(ppm)
    except Exception:
        return None


def frame_3d(app, out, W, H, cx, cy):
    """Render the 3D particle layer small. Returns (w, h, floats) or None."""
    import particle_studio as PS
    gl = get_gl()
    if gl is None or out is None or not len(out["x"]):
        return None
    try:
        from render.gl_view import mat_clip_3d as _clip, orbit_right_up as _ru
        import math
        rw, rh = raster_size(W, H)
        k = rw / max(1.0, float(W))
        fov = float(getattr(app, "fov", 60.0))
        focal = ((max(100, H) * 0.5) / max(0.05, math.tan(math.radians(fov / 2))))
        zoom = app.cam["zoom"]
        n = len(out["x"])
        xs, zs, rs = out["wx"], out["z"], out["r"]
        ys, cs, ss = out["wy"], out["color"], out["shape"]
        aa = out.get("alpha", None)
        buckets = {}
        glow = []
        for i in range(n):
            c = cs[i]
            t = (xs[i], ys[i], zs[i], rs[i] * k,
                 ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0,
                 (c & 255) / 255.0, aa[i] if aa else 1.0)
            buckets.setdefault(PS.SHAPE_ORDER[ss[i]], []).append(t)
            glow.append(t)
        try:
            glow_on = bool(app.glow)
        except Exception:
            glow_on = True
        if not (glow_on and n <= 450):
            glow = []
        ru, uu = _ru(app.cam["yaw"], app.cam["pitch"])
        clip = _clip(app.cam["yaw"], app.cam["pitch"], zoom, focal,
                     rw, rh, cx * k, cy * k,
                     app.cam["ox"] * k, app.cam["oy"] * k)
        ppm = gl.render(buckets, glow, rw, rh, ortho=0, clip=clip,
                        zoom=zoom, focal=focal, right=ru, up=uu,
                        bg=(20 / 255, 21 / 255, 28 / 255),
                        grid=PS.StudioApp._gl_grid_3d(),
                        blend=(app.em.get("blendingMode")
                               if isinstance(getattr(app, "em", None), dict)
                               and app.em.get("blendingMode") in PS.BLEND_MODES
                               else "Normal"))
        return ppm_to_floats(ppm)
    except Exception:
        return None
