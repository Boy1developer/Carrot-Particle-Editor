# -*- coding: utf-8 -*-
"""Ribbon-strip math for trail rendering (pure logic, no Dear PyGui).

The viewport paint functions in studio_imgui.py are thin draw-call loops
over these helpers, so every silhouette rule below is unit-testable
headless. Conventions (match the effect JSON):

- ``t`` runs 0 at the head (newest point) to 1 at the tail (oldest).
- width(t) = lerp(widthStart, widthEnd, t) * widthCurve(t) * widthMult,
  with taperHead/taperTail pinching the ends and minScreenWidth flooring
  the result (px; the DPG drawlist is 1:1 pixels). No hairlines, ever.
- color(t) comes from the baked 256-entry gradient LUT (head -> tail).
- The outer strip mixes the gradient toward edgeColor; the inner core
  strip (coreWidth fraction) uses coreColor (or a brightened gradient
  when coreColor is empty). Glow is one wide low-alpha pass underneath.
- flicker {amount, hz} modulates alpha with a per-trail phase so bolts
  re-strike instead of sitting static.
"""

import math

HEAD = 0
TAIL = 1

#: hard cap of strip segments per trail per layer (bounds DPG draws)
MAX_SEGS = 8

#: raw input points are pre-strided to this many before smoothing
#: (bounds the Python-side geometry work per trail per frame)
MAX_INPUT_PTS = 24


def pre_stride(pts, max_pts=MAX_INPUT_PTS):
    """(segments, core_on): full quality for a few trails, graceful
    degradation as counts grow (DPG draws stay bounded)."""
    if n <= 8:
        return (8, True)
    if n <= 24:
        return (5, True)
    return (3, False)
    """Cap raw trail points (endpoints kept) before smoothing."""
    n = len(pts)
    if n <= max_pts:
        return list(pts)
    return [pts[i] for i in stride_indices(n, max_pts - 1)]


def _hex(s, fb=(255, 255, 255)):
    h = str(s or "").lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    try:
        n = int(h[:6], 16)
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    except (ValueError, TypeError):
        return tuple(fb)


def _num(tcfg, key, fb):
    try:
        return float(tcfg.get(key, fb))
    except (ValueError, TypeError, AttributeError):
        return float(fb)


def _bool(tcfg, key, fb=False):
    try:
        return bool(tcfg.get(key, fb))
    except AttributeError:
        return bool(fb)


def resolve_style(tcfg):
    """Flatten a trails block into render-ready style (pure)."""
    tcfg = tcfg if isinstance(tcfg, dict) else {}
    core = str(tcfg.get("coreColor") or "").strip()
    return {
        "widthStart": _num(tcfg, "widthStart", 8.0),
        "widthEnd": _num(tcfg, "widthEnd", 1.0),
        "widthMult": _num(tcfg, "widthMult", 1.0),
        "taperHead": _bool(tcfg, "taperHead"),
        "taperTail": _bool(tcfg, "taperTail", True),
        "minScreenWidth": max(0.0, _num(tcfg, "minScreenWidth", 2.5)),
        "edgeColor": _hex(tcfg.get("edgeColor") or "#ffffff"),
        "hasCore": bool(core),
        "coreColor": _hex(core or "#ffffff"),
        "coreWidth": max(0.0, min(1.0, _num(tcfg, "coreWidth", 0.35))),
        "edgeSoftness": max(0.0, min(1.0, _num(tcfg, "edgeSoftness", 0.6))),
        "glowWidth": max(0.0, _num(tcfg, "glowWidth", 0.0)),
        "glowAlpha": max(0.0, min(1.0, _num(tcfg, "glowAlpha", 0.0))),
        "intensity": max(0.0, _num(tcfg, "intensity", 1.0)),
        "flickerAmt": max(0.0, min(1.0, _num(tcfg, "flickerAmt", 0.0))),
        "flickerHz": max(0.0, _num(tcfg, "flickerHz", 8.0)),
        "hideParticle": _bool(tcfg, "hideParticle", True),
    }


def width_at(t, style, wlut):
    """Full ribbon width (px, before the minScreenWidth floor)."""
    try:
        curve = float(wlut[max(0, min(63, int(t * 63)))])
    except (IndexError, TypeError, ValueError):
        curve = 1.0
    w = (style["widthStart"] + (style["widthEnd"] - style["widthStart"])
         * t) * curve * style["widthMult"]
    if style["taperHead"]:
        w *= min(1.0, max(0.0, t / 0.06))
    if style["taperTail"]:
        w *= min(1.0, max(0.0, (1.0 - t) / 0.06))
    return max(0.0, w)


def floored_width(t, style, wlut):
    """Width actually drawn (minScreenWidth floor applied)."""
    return max(style["minScreenWidth"], width_at(t, style, wlut))


def lut_color(grad, t):
    """(r, g, b, a) from a baked 256-entry gradient at t in [0, 1]."""
    try:
        return tuple(grad[max(0, min(255, int(t * 255)))])
    except (IndexError, TypeError, ValueError):
        return (255, 255, 255, 255)


def mix(c1, c2, u):
    """Lerp two rgb triples (u = 0 keeps c1)."""
    u = max(0.0, min(1.0, u))
    return (c1[0] + (c2[0] - c1[0]) * u,
            c1[1] + (c2[1] - c1[1]) * u,
            c1[2] + (c2[2] - c1[2]) * u)


def outer_color(grad_rgb, style, intensity=1.0):
    """Edge-mixed strip color (rgb floats, alpha handled separately)."""
    r, g, b = mix(grad_rgb, style["edgeColor"], 0.5)
    k = intensity * style["intensity"]
    return (min(255.0, r * k), min(255.0, g * k), min(255.0, b * k))


def core_color(grad_rgb, style):
    """Inner core color: explicit coreColor, else brightened gradient."""
    if style["hasCore"]:
        r, g, b = (float(v) for v in style["coreColor"])
    else:
        r, g, b = (min(255.0, v * 1.25 + 20.0) for v in grad_rgb)
    k = style["intensity"]
    return (min(255.0, r * k), min(255.0, g * k), min(255.0, b * k))


def outer_alpha(grad_alpha, style):
    """Softer edges fade the outer strip; hard edges keep it solid."""
    return grad_alpha * (0.55 + 0.45 * (1.0 - style["edgeSoftness"]))


def flicker_factor(now_s, hz, amt, phase):
    """Alpha multiplier in [1-amt, 1] (amt = 0 disables)."""
    if amt <= 0.0 or hz <= 0.0:
        return 1.0
    return 1.0 - amt * 0.5 * (1.0 + math.sin(
        2.0 * math.pi * (hz * now_s + phase)))


def stride_indices(n, max_segs=MAX_SEGS):
    """Evenly strided indices covering [0, n-1] (endpoints included)."""
    if n <= 1:
        return [0]
    if n - 1 <= max_segs:
        return list(range(n))
    step = (n - 1) / max_segs
    idx = [int(round(i * step)) for i in range(max_segs + 1)]
    idx[-1] = n - 1
    return sorted(set(idx))


def detail_for_count(n):
    """(segments, core_on): full quality for a few trails, graceful
    degradation as counts grow (DPG draws stay bounded)."""
    if n <= 8:
        return (8, True)
    if n <= 24:
        return (5, True)
    return (3, False)


def pre_stride(pts, max_pts=MAX_INPUT_PTS):
    """Cap raw trail points (endpoints kept) before smoothing."""
    n = len(pts)
    if n <= max_pts:
        return list(pts)
    return [pts[i] for i in stride_indices(n, max_pts - 1)]


def build_ribbon(pts, widths):
    """Offset outline (left[], right[]) of a polyline strip (2D)."""
    left, right = [], []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        ax, ay = pts[max(0, i - 1)]
        bx, by = pts[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        leng = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / leng, dx / leng
        hw = max(0.0, widths[i]) * 0.5
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))
    return left, right


def seg_quad(left, right, i):
    """Filled quad between strip stations i and i+1 (both layers)."""
    return [left[i], right[i], right[i + 1], left[i + 1]]
