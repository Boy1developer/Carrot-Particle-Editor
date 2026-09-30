# -*- coding: utf-8 -*-
"""
Particle Studio Pro - Python GUI exporter (ParticleFX-style dark UI)
Compatible with AdvancedParticleEmitter GDevelop extension, format v1.0 type 2d/3d.
Stdlib only (tkinter). Run: python editor/particle_studio.py
"""
import base64
import copy
import json
import math
import os
import random
import struct
import sys
import threading
import time
import traceback
import webbrowser
import tkinter as tk
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from tkinter import filedialog, messagebox, colorchooser

# Repo layout: this file lives in editor/; the repo root (particle_core.pyd,
# render/, preview/, assets/) is added to sys.path when running from source.
# Frozen exe bundles everything, so skip the tweak there.
if not getattr(sys, "frozen", False):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

try:
    from contracts.gen.contracts import (
        EXPORT_VERSION as _GEN_VERSION,
        SHAPE_ORDER as _GEN_SHAPE_ORDER,
        SHAPES_2D as _GEN_SHAPES_2D,
        SHAPES_3D as _GEN_SHAPES_3D,
        EASINGS as _GEN_EASINGS,
        EASING_ALIASES as _GEN_EASING_ALIASES,
        BLEND_MODES as _GEN_BLEND_MODES,
    )
    _HAVE_CONTRACTS = True
except Exception:
    _HAVE_CONTRACTS = False

try:
    import particle_core as _CPP_MOD  # C++ sim core (optional, built via core/build_core.py)
    HAS_CPP_CORE = True
    SHAPE_ORDER = list(_CPP_MOD.SHAPE_ORDER)
except Exception:
    _CPP_MOD = None
    HAS_CPP_CORE = False
    SHAPE_ORDER = list(_GEN_SHAPE_ORDER) if _HAVE_CONTRACTS else [
        "circle", "square", "triangle", "star", "diamond", "line",
        "custom", "sphere", "cube", "pyramid", "torus", "billboard"]
try:
    from render.gl_view import GLView, mat_clip_3d, mat_ortho, orbit_right_up
    HAS_GL_VIEW = True
except Exception:
    HAS_GL_VIEW = False

VERSION = _GEN_VERSION if _HAVE_CONTRACTS else "1.0"  # effect JSON format (extension contract — do NOT bump with the app)
APP_VERSION = "0.1.1"  # Carrot Particle Editor release version (title bar)
BUILD_ID = "b20260930-extcompat"  # bump on every shipped change; shown in title


def debug_log(*parts):
    """Append-only diagnostics file (works frozen: TEMP dir). Never raises."""
    try:
        p = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                         "carrot_debug.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") +
                    " ".join(str(x) for x in parts) + "\n")
    except Exception:
        pass


def app_base_dir():
    """Bundle dir holding preview/assets: frozen exe -> sys._MEIPASS,
    else the repo root (parent of editor/). (Frozen __file__/CWD are
    unreliable.)"""
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(meipass):
            return meipass
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)  # editor/ -> repo root
    return root if os.path.isdir(os.path.join(root, "preview")) else here

EASINGS = list(_GEN_EASINGS) if _HAVE_CONTRACTS else ["linear", "ease-in", "ease-out", "ease-in-out"]
EASING_ALIASES = dict(_GEN_EASING_ALIASES) if _HAVE_CONTRACTS else {"easeIn": "ease-in", "easeOut": "ease-out", "easeInOut": "ease-in-out"}
BLEND_MODES = list(_GEN_BLEND_MODES) if _HAVE_CONTRACTS else ["Normal", "Additive", "Subtractive", "Multiply"]
MODES = ["Infinite", "Burst", "One Shot"]
FLOW_MODES = ["rate", "interval"]
SHAPES_2D = list(_GEN_SHAPES_2D) if _HAVE_CONTRACTS else ["circle", "square", "triangle", "star", "diamond", "line", "custom"]
SHAPES_3D = list(_GEN_SHAPES_3D) if _HAVE_CONTRACTS else ["sphere", "cube", "pyramid", "diamond", "torus",
             "square", "triangle", "star", "line", "billboard", "custom"]
ZONE_2D = ["Circle", "Rectangle", "Point", "Line"]
ZONE_3D = ["sphere", "box", "point", "line"]
ZONE_MODE = ["Surface", "Edge"]

# ---------- palette (matches screenshot) ----------
BG      = "#1a1b22"   # viewport surround / window
SIDEBAR = "#22232e"   # left panel
CARD    = "#262733"   # inputs row bg
INPUT   = "#14151c"   # entry bg
BORDER  = "#353646"   # subtle borders
TEXT    = "#e8e8ee"
MUTED   = "#9a9aad"
ACCENT  = "#7b61ff"   # purple pills
ACCENT2 = "#4d9fff"   # blue logo
OK      = "#3ddc84"
WARN    = "#ff5c5c"
YELLOW  = "#e8d44d"   # cone wireframe
CHOOSER_BG = "#101218"   # startup page near-black (matches mockup)
CHOOSER_CARD = "#22262f"  # 2D/3D cards
CHOOSER_ICON_BG = "#2e333d"  # icon tile inside cards

FONT      = ("Segoe UI", 10)
FONT_SM   = ("Segoe UI", 9)
FONT_SEC  = ("Segoe UI", 8, "bold")
FONT_LOGO = ("Segoe UI", 12, "bold")


FONT      = ("Segoe UI", 10)
FONT_SM   = ("Segoe UI", 9)
FONT_SEC  = ("Segoe UI", 8, "bold")
FONT_LOGO = ("Segoe UI", 12, "bold")


def _point_in_poly(px, py, pts):
    """Even-odd point-in-polygon for flat [x0,y0,x1,y1,...]."""
    inside = False
    n = len(pts) // 2
    for i in range(n):
        x1, y1 = pts[2 * i], pts[2 * i + 1]
        x2, y2 = pts[2 * ((i + 1) % n)], pts[2 * ((i + 1) % n) + 1]
        if (y1 > py) != (y2 > py):
            xin = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < xin:
                inside = not inside
    return inside


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    t = 0.0 if n < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / n))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def build_app_icon_png(size=64):
    """Procedural app icon (Carrot mark: dark panel + orbit + carrot), pure
    stdlib PNG encoder (zlib+struct). Returns PNG bytes (RGBA). Used for the
    window/taskbar icon when no assets/app_icon.png file is present."""
    import struct
    import zlib
    S = size
    buf = bytearray(S * S * 4)

    def put(x, y, r, g, b, a=255):
        x, y = int(x), int(y)
        if 0 <= x < S and 0 <= y < S and a > 0:
            o = (y * S + x) * 4
            if a >= buf[o + 3]:
                buf[o:o + 4] = bytes((r, g, b, a))

    def disc(cx, cy, r, col):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if math.hypot(x - cx, y - cy) <= r:
                    put(x, y, *col)

    u = S / 64.0  # design units (artwork authored at 64px)
    # dark rounded panel
    x0, y0, x1, y1, cr = 9 * u, 15 * u, 55 * u, 51 * u, 7 * u
    for y in range(int(y0), int(y1) + 1):
        for x in range(int(x0), int(x1) + 1):
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            if math.hypot(dx, dy) <= cr:
                put(x, y, 20, 22, 29)
    # grid lines
    gx = x0 + 4 * u
    while gx < x1 - 2 * u:
        for y in range(int(y0 + 3 * u), int(y1 - 2 * u)):
            put(gx, y, 34, 40, 56)
        gx += 6 * u
    gy = y0 + 4 * u
    while gy < y1 - 2 * u:
        for x in range(int(x0 + 3 * u), int(x1 - 2 * u)):
            put(x, y, 34, 40, 56)
        gy += 6 * u
    # traffic dots
    for i, col in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        disc(x0 + (5 + i * 6) * u, y0 + 4 * u, 2.2 * u, col)
    # orbit ellipse (rotated): yellow core + orange halo
    ocx, ocy, rx, ry, rot = 32 * u, 33 * u, 22 * u, 8 * u, math.radians(-18)
    co, si = math.cos(rot), math.sin(rot)
    for y in range(S):
        for x in range(S):
            dx, dy = (x - ocx) / rx, (y - ocy) / ry
            xp, yp = dx * co - dy * si, dx * si + dy * co
            d = abs(math.hypot(xp, yp) - 1) * min(rx, ry)
            if d < 1.1 * u:
                put(x, y, 255, 201, 60)
            elif d < 2.4 * u:
                put(x, y, 255, 130, 0)
    # glow dots
    for dx, dy, r in ((-19, -2, 2.2), (19, -9, 2.2), (15, 1, 1.6),
                      (-13, 5, 1.6), (21, 9, 2.6), (-11, 13, 2.2)):
        disc(ocx + dx * u, ocy + dy * u, r * u, (255, 179, 0))
    # carrot diamond halves
    T, R, B, L = (32 * u, 19 * u), (44 * u, 32 * u), (32 * u, 52 * u), (20 * u, 32 * u)
    right = (T[0], T[1], R[0], R[1], B[0], B[1])
    left = (T[0], T[1], B[0], B[1], L[0], L[1])
    for y in range(int(T[1]), int(B[1]) + 1):
        for x in range(int(L[0]), int(R[0]) + 1):
            if _point_in_poly(x, y, right):
                put(x, y, 255, 128, 0)
            elif _point_in_poly(x, y, left):
                put(x, y, 194, 94, 0)
    # diamond outline
    for a, b in ((T, R), (R, B), (B, L), (L, T)):
        for y in range(int(min(a[1], b[1]) - 1), int(max(a[1], b[1]) + 2)):
            for x in range(int(min(a[0], b[0]) - 1), int(max(a[0], b[0]) + 2)):
                if _seg_dist(x, y, *a, *b) < 1.1 * u:
                    put(x, y, 0, 0, 0)
    # green spiky crown
    ccx, ccy, Rout, rin, nsp = 32 * u, 17 * u, 13 * u, 8 * u, 9
    star = []
    for i in range(nsp * 2):
        a = -math.pi / 2 + i * math.pi / nsp
        rr = Rout if i % 2 == 0 else rin
        star += [ccx + math.cos(a) * rr, ccy + math.sin(a) * rr]
    for y in range(int(ccy - Rout - 1), int(T[1]) + 2):
        for x in range(int(ccx - Rout - 1), int(ccx + Rout + 2)):
            if _point_in_poly(x, y, star):
                put(x, y, 0, 228, 54)
    for i in range(nsp * 2):
        a = (star[2 * i], star[2 * i + 1])
        b = (star[2 * ((i + 1) % (nsp * 2))], star[2 * ((i + 1) % (nsp * 2)) + 1])
        for y in range(int(min(a[1], b[1]) - 1), int(max(a[1], b[1]) + 2)):
            for x in range(int(min(a[0], b[0]) - 1), int(max(a[0], b[0]) + 2)):
                if _seg_dist(x, y, *a, *b) < 1.0 * u:
                    put(x, y, 0, 0, 0)

    raw = b"".join(b"\x00" + bytes(buf[y * S * 4:(y + 1) * S * 4]) for y in range(S))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw))) +
            chunk(b"IEND", b""))


def _mesh_bearing_names(g):
    """Named nodes whose subtree holds >= 1 mesh (bone-only nodes excluded).

    Riggers (Godot robot: 30 bones, 0 mesh-bearing) would otherwise fill
    the picker with nodes that can never render anything.
    """
    try:
        nodes = g.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            return []
        mesh_at = [False] * len(nodes)
        for i, n in enumerate(nodes):
            if isinstance(n, dict) and n.get("mesh") is not None:
                try:
                    m = int(n["mesh"])
                    if 0 <= m < len(g.get("meshes", [])):
                        mesh_at[i] = True
                except (ValueError, TypeError):
                    pass
        out = []
        for i, n in enumerate(nodes):
            if not isinstance(n, dict) or not n.get("name"):
                continue
            stack, hit = [i], False
            while stack and not hit:
                cur = stack.pop()
                if not (0 <= cur < len(nodes)):
                    continue
                if mesh_at[cur]:
                    hit = True
                    break
                try:
                    ch = nodes[cur].get("children", [])
                except AttributeError:
                    continue
                stack.extend(c for c in ch if isinstance(c, int))
            if hit:
                out.append(str(n["name"]))
            if len(out) >= 64:
                break
        return out
    except Exception:
        return []


def model_nodes_from_file(path):
    """GLB/GLTF node names via stdlib (struct+json). Returns list (maybe empty).

    Only mesh-bearing nodes (see _mesh_bearing_names); the full JSON
    chunk is read (some rigged exports carry ~350K of node JSON, far
    past the old 64K peek window).
    """
    try:
        if path.lower().endswith(".gltf"):
            with open(path, encoding="utf-8") as f:
                g = json.load(f)
            return _mesh_bearing_names(g)
        with open(path, "rb") as f:
            head = f.read(20)
            if head[:4] != b"glTF" or head[16:20] != b"JSON":
                return []
            jlen = struct.unpack("<I", head[12:16])[0]
            if jlen <= 0 or jlen > 200 * 1024 * 1024:
                return []
            js = f.read(jlen)
            if len(js) != jlen:
                return []
        g = json.loads(js.decode("utf-8", "replace"))
        return _mesh_bearing_names(g)
    except Exception:
        return []


def model_blobs_for_states(states, cap_mb=8):
    """{ref: {mime, file, data64}} for custom-model states (preview embed).

    Reads GLB/GLTF bytes for states carrying a customModel with a real
    file path; skips missing files, unsupported extensions, and files
    over cap_mb. ref follows current_effect()'s modelRefs convention so
    the browser preview can match blobs to states.
    """
    out = {}
    cap = max(1, int(cap_mb)) * 1024 * 1024
    for s in states or []:
        try:
            cm = s.get("customModel") or {}
            path = cm.get("path") or ""
            if not path or not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext == ".glb":
                mime = "model/gltf-binary"
            elif ext == ".gltf":
                mime = "model/gltf+json"
            else:
                continue
            if os.path.getsize(path) > cap:
                continue
            ref = ((s.get("modelRefs") or [""])[0]
                   or cm.get("node")
                   or os.path.splitext(os.path.basename(path))[0])
            if not ref or ref in out:
                continue
            with open(path, "rb") as f:
                data = f.read()
            if not data or len(data) > cap:
                continue
            out[ref] = {"mime": mime, "file": os.path.basename(path),
                        "data": base64.b64encode(data).decode("ascii")}
        except Exception:
            continue
    return out


def model_fingerprint(states):
    """Cheap (path, mtime, size) snapshot to detect model-set changes."""
    fp = []
    for s in states or []:
        cm = s.get("customModel") or {}
        p = cm.get("path") or ""
        if not p:
            continue
        try:
            st = os.stat(p)
            fp.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            fp.append((p, -1, -1))
    return tuple(fp)


def default_state(role="intermediate", idx=0):
    if role == "birth":
        return {
            "id": f"state_{idx}", "role": "birth", "label": "birth",
            "duration": 0.5, "shape": "circle", "easing": "linear",
            "starPoints": 5, "starInnerRatio": 0.4,
            "appearance": {"size": 8, "sizeMax": 12, "color": "#ffaa00", "opacity": 255},
            "movement": {"minSpeed": 60, "maxSpeed": 160, "minRot": -90, "maxRot": 90},
            "customShapeRefs": [],
        }
    if role == "death":
        return {
            "id": f"state_{idx}", "role": "death", "label": "death",
            "duration": 0.5, "shape": "circle", "easing": "ease-out",
            "starPoints": 5, "starInnerRatio": 0.4,
            "appearance": {"size": 2, "sizeMax": 4, "color": "#ff3300", "opacity": 0},
            "movement": {"minSpeed": 20, "maxSpeed": 60, "minRot": -90, "maxRot": 90},
            "customShapeRefs": [],
        }
    return {
        "id": f"state_{idx}", "role": "intermediate", "label": f"mid{idx}",
        "duration": 0.5, "shape": "circle", "easing": "linear",
        "starPoints": 5, "starInnerRatio": 0.4,
        "appearance": {"size": 10, "sizeMax": 14, "color": "#ffdd44", "opacity": 200},
        "movement": {"minSpeed": 40, "maxSpeed": 120, "minRot": -90, "maxRot": 90},
        "customShapeRefs": [],
    }


def default_emitter(ptype="2d"):
    if ptype == "3d":
        return {
            "flow": 40, "flowMode": "rate", "flowInterval": 1,
            "maxParticles": 300, "reservoir": 50, "mode": "Infinite",
            "reverse": False, "alignDir": False, "billboard": True,
            "rotationMode": "speed",
            "gravity": {"x": 0, "y": 0, "z": 0},
            "emissionZone": {"shape": "sphere", "radius": 10, "width": 100,
                             "height": 60, "depth": 60, "length": 100,
                             "rotationX": 0, "rotationY": 0, "rotationZ": 0,
                             "mode": "Surface", "showZone": True},
            "propagationCone": {"directionX": 0, "directionY": 0,
                                "directionZ": 0, "spread": 90, "showCone": True},
            "blendingMode": "Normal",
        }
    return {
        "flow": 40, "flowMode": "rate", "flowInterval": 1,
        "maxParticles": 300, "reservoir": 50, "mode": "Infinite",
        "reverse": False, "alignDir": False,
        "rotationMode": "speed",
        "gravity": {"x": 0, "y": 0},
        "emissionZone": {"shape": "Circle", "rotation": 0, "radius": 10,
                         "width": 100, "height": 60, "length": 100,
                         "mode": "Surface", "showZone": True},
        "propagationCone": {"direction": 0, "spread": 90, "showCone": True},
        "blendingMode": "Normal",
    }


def build_effect(ptype, emitter, states):
    return {"version": VERSION, "type": ptype, "emitter": emitter, "states": states}


def effect_models_block(src_states, out_states):
    """Top-level `models` block for the GDevelop extension, or None.

    Maps ref -> GLB node name; whole-file picks map to "" and the
    extension resolves those to the full scene (a bogus node name would
    only warn in-game). First custom-model state wins (single GLB).
    """
    for src, st in zip(src_states or [], out_states or []):
        try:
            cm = src.get("customModel") or {}
            if not cm.get("file"):
                continue
            ref = (st.get("modelRefs") or [""])[0] or cm.get("node") or ""
            if not ref:
                continue
            return {"file": cm["file"],
                    "nodes": list(cm.get("nodes") or []),
                    "map": {ref: cm.get("node") or ""}}
        except Exception:
            continue
    return None


def validate_effect(eff):
    errs = []
    if eff.get("version") != "1.0":
        errs.append("version لازم تكون '1.0'")
    if eff.get("type") not in ("2d", "3d"):
        errs.append("type لازم 2d او 3d")
    if not isinstance(eff.get("emitter"), dict):
        errs.append("emitter ناقص")
        return errs
    states = eff.get("states")
    if not isinstance(states, list) or len(states) < 2:
        errs.append("لازم على الاقل 2 states (birth + death)")
    else:
        roles = [s.get("role") for s in states]
        if "birth" not in roles:
            errs.append("لازم state role=birth")
        if "death" not in roles:
            errs.append("لازم state role=death")
        for s in states:
            if s.get("easing") not in EASINGS:
                errs.append(f"easing غلط في {s.get('label')}")
            if str(s.get("shape", "")).lower() == "custom" and not (s.get("modelRefs") or s.get("customShapeRefs")):
                errs.append(f"custom بدون موديل في {s.get('label')} (ارفع ملف)")
    errs.extend(validate_against_schema(eff))
    return errs


def _contracts_schema():
    """Load contracts/gen/schema.json (cached). Falls back to {} (skip)."""
    global _SCHEMA_CACHE
    try:
        _SCHEMA_CACHE
    except NameError:
        _SCHEMA_CACHE = None
    if _SCHEMA_CACHE is None:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            p = os.path.join(os.path.dirname(here), "contracts", "gen", "schema.json")
            with open(p, encoding="utf-8") as f:
                _SCHEMA_CACHE = json.load(f)
        except Exception:
            _SCHEMA_CACHE = {}
    return _SCHEMA_CACHE


def _schema_check(schema, data, path="$", errs=None):
    """Minimal stdlib-only JSON Schema check (type/required/enum/properties/items/minItems).

    Unknown keys are ignored so newer files stay loadable (forward compatible).
    """
    if errs is None:
        errs = []
    if not isinstance(schema, dict):
        return errs
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict):
            errs.append(f"{path}: لازم object")
            return errs
    elif t == "array":
        if not isinstance(data, list):
            errs.append(f"{path}: لازم array")
            return errs
    elif t == "string":
        if not isinstance(data, str):
            errs.append(f"{path}: لازم string")
            return errs
    elif t == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errs.append(f"{path}: لازم number")
            return errs
    elif t == "boolean":
        if not isinstance(data, bool):
            errs.append(f"{path}: لازم boolean")
            return errs
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: قيمة غير مدعومة {data!r}")
    if isinstance(data, dict):
        for k in schema.get("required", []):
            if k not in data:
                errs.append(f"{path}: ناقص '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                _schema_check(sub, data[k], f"{path}.{k}", errs)
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errs.append(f"{path}: لازم على الاقل {schema['minItems']} عناصر")
        sub = schema.get("items")
        if isinstance(sub, dict):
            for i, v in enumerate(data):
                _schema_check(sub, v, f"{path}[{i}]", errs)
    return errs


def validate_against_schema(eff):
    """Validate an effect dict against contracts/gen/schema.json. Returns [errors]."""
    schema = _contracts_schema()
    if not schema:
        return []
    try:
        return _schema_check(schema, eff)
    except Exception as e:  # never let validation itself crash the UI
        return [f"schema check failed: {e}"]


def migrate_effect(data):
    """Migrate an old/foreign effect dict to the current export format.

    Returns (migrated_dict, warnings). Raises ValueError on a dict that
    cannot be migrated (not an object, or an explicitly newer version).
    Rules: missing version -> current (warn); easing aliases
    (easeIn/easeOut/easeInOut) -> hyphenated (warn each); missing easing ->
    linear (warn); shapes lowercased; missing emitter.blendingMode -> Normal.
    """
    if not isinstance(data, dict):
        raise ValueError("effect file must contain a JSON object")
    eff = copy.deepcopy(data)
    warns = []
    v = eff.get("version")
    if v is None:
        eff["version"] = VERSION
        warns.append(f"version missing -> assumed '{VERSION}'")
    elif str(v) != str(VERSION):
        raise ValueError(f"unsupported effect version {v!r} (need '{VERSION}')")
    if eff.get("type") not in ("2d", "3d"):
        eff["type"] = "2d"
        warns.append("type missing/unknown -> '2d'")
    em = eff.get("emitter")
    if not isinstance(em, dict):
        eff["emitter"] = em = {}
        warns.append("emitter missing -> {}")
    if not em.get("blendingMode"):
        em["blendingMode"] = "Normal"
    states = eff.get("states")
    if isinstance(states, list):
        for i, s in enumerate(states):
            if not isinstance(s, dict):
                continue
            ez = s.get("easing")
            if ez in EASING_ALIASES:
                s["easing"] = EASING_ALIASES[ez]
                warns.append(f"states[{i}].easing '{ez}' -> '{s['easing']}'")
            elif ez not in EASINGS:
                s["easing"] = "linear"
                warns.append(f"states[{i}].easing missing/unknown -> 'linear'")
            if isinstance(s.get("shape"), str):
                s["shape"] = s["shape"].lower()
    return eff, warns


def _boom_states(shape):
    return [
        {"id": "s0", "role": "birth", "label": "birth", "duration": 0.4,
         "shape": shape, "easing": "ease-out", "starPoints": 5, "starInnerRatio": 0.4,
         "appearance": {"size": 14, "sizeMax": 22, "color": "#ffff88", "opacity": 255},
         "movement": {"minSpeed": 150, "maxSpeed": 350, "minRot": -180, "maxRot": 180},
         "customShapeRefs": []},
        {"id": "s1", "role": "death", "label": "death", "duration": 0.6,
         "shape": shape, "easing": "ease-in", "starPoints": 5, "starInnerRatio": 0.4,
         "appearance": {"size": 2, "sizeMax": 6, "color": "#ff4400", "opacity": 0},
         "movement": {"minSpeed": 30, "maxSpeed": 80, "minRot": -180, "maxRot": 180},
         "customShapeRefs": []},
    ]


TEMPLATES = {
    # each template carries a 2D and a 3D version; applied to the ACTIVE editor
    "Explosion": {
        "2d": {"flow": 120, "maxParticles": 400, "reservoir": 150, "mode": "Burst",
               "gravity": {"x": 0, "y": 300},
               "emissionZone": {"shape": "Circle", "radius": 10, "mode": "Surface"},
               "propagationCone": {"direction": 0, "spread": 360}},
        "3d": {"flow": 120, "maxParticles": 400, "reservoir": 150, "mode": "Burst",
               "gravity": {"x": 0, "y": -300, "z": 0},
               "emissionZone": {"shape": "sphere", "radius": 10, "mode": "Surface"},
               "propagationCone": {"directionZ": 0, "directionY": 0, "spread": 360}},
        "states2d": None,  # filled below (needs function defined above)
        "states3d": None,
    },
    "Fire": {
        "2d": {"flow": 60, "maxParticles": 300, "reservoir": 50, "mode": "Infinite",
               "gravity": {"x": 0, "y": -150},
               "emissionZone": {"shape": "Rectangle", "width": 60, "height": 10, "mode": "Surface"},
               "propagationCone": {"direction": 0, "spread": 30}},
        "3d": {"flow": 60, "maxParticles": 300, "reservoir": 50, "mode": "Infinite",
               "gravity": {"x": 0, "y": 150, "z": 0},
               "emissionZone": {"shape": "box", "width": 60, "height": 10, "depth": 10, "mode": "Surface"},
               "propagationCone": {"directionZ": 0, "directionY": 90, "spread": 30}},
    },
    "Rain": {
        "2d": {"flow": 200, "maxParticles": 600, "reservoir": 100, "mode": "Infinite",
               "gravity": {"x": 0, "y": 900},
               "emissionZone": {"shape": "Line", "length": 800, "mode": "Surface"},
               "propagationCone": {"direction": 90, "spread": 5}},
        "3d": {"flow": 200, "maxParticles": 600, "reservoir": 100, "mode": "Infinite",
               "gravity": {"x": 0, "y": -900, "z": 0},
               "emissionZone": {"shape": "line", "length": 800, "mode": "Surface"},
               "propagationCone": {"directionZ": 0, "directionY": -90, "spread": 5}},
    },
    "Snow": {
        "2d": {"flow": 50, "maxParticles": 400, "reservoir": 50, "mode": "Infinite",
               "gravity": {"x": 20, "y": 60},
               "emissionZone": {"shape": "Line", "length": 800, "mode": "Surface"},
               "propagationCone": {"direction": 90, "spread": 15}},
        "3d": {"flow": 50, "maxParticles": 400, "reservoir": 50, "mode": "Infinite",
               "gravity": {"x": 20, "y": -60, "z": 0},
               "emissionZone": {"shape": "line", "length": 800, "mode": "Surface"},
               "propagationCone": {"directionZ": 0, "directionY": -90, "spread": 15}},
    },
}
TEMPLATES["Explosion"]["states2d"] = _boom_states("circle")
TEMPLATES["Explosion"]["states3d"] = _boom_states("sphere")


# =====================================================================
class _QuietHTTPHandler(SimpleHTTPRequestHandler):
    """No stderr logging: frozen windowed exe has no console (sys.stderr is
    None) and the first log call would kill the connection with zero bytes."""

    def log_message(self, *args):
        pass


class _PreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass  # same reason: never touch missing stderr, just keep serving


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Carrot Particle Editor v{APP_VERSION} [{BUILD_ID}]")
        debug_log("boot", BUILD_ID, "frozen=", getattr(sys, "frozen", False))
        self.geometry("1280x800")
        self.configure(bg=CHOOSER_BG)
        try:  # window/taskbar icon: exact file wins, else procedural mark
            ip = os.path.join(app_base_dir(), "assets", "app_icon.png")
            if os.path.isfile(ip):
                self._icon_img = tk.PhotoImage(file=ip)
            else:
                import base64
                self._icon_img = tk.PhotoImage(
                    data=base64.b64encode(build_app_icon_png(64)).decode("ascii"))
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass
        self.option_add("*Font", FONT)
        self.filename = "Default"
        self.filepath = None
        self.ptype = "2d"
        self._cached_eff = None
        self._cache_t = 0.0
        self._eff_dirty = True
        self._last_sim_mode = None
        self._cpp_eng = None  # lazy C++ Engine (None => pure-Python fallback)
        self._cpp_key = None
        self._cpp_out = None
        # undo/redo history
        self._history = []
        self._hidx = -1
        self._restoring = False
        self._debounce_after = None
        self._loading = False  # True while show_state fills the form (no persist)
        self._preview_tab_opened = False  # Three.js viewport auto-opened once
        self.states = [default_state("birth", 0), default_state("death", 1)]
        self.sel_state = 0
        self._editor_built = False
        self._show_chooser()

    # ================= startup mode chooser =================
    def _logo_photo(self, target_h):
        """Use assets/app_icon.png (exact artwork, if the user drops it in)
        else carrot_logo.png / carrot.png / logo.png next to the script.
        Returns PhotoImage or None (vector fallback)."""
        base = app_base_dir()
        for name in ("assets/app_icon.png", "carrot_logo.png", "carrot.png", "logo.png"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                try:
                    img = tk.PhotoImage(file=p)
                    if img.height() > target_h and target_h > 0:
                        f = max(1, img.height() // target_h)
                        img = img.subsample(f, f)
                    if not hasattr(self, "_logo_imgs"):
                        self._logo_imgs = []
                    self._logo_imgs.append(img)  # keep ref (anti-GC)
                    return img
                except Exception:
                    return None
        return None

    def _sparkle(self, cv, cx, cy, r, fill="#ffd54a"):
        """4-point sparkle."""
        try:
            cv.create_polygon(cx, cy - r, cx + r * 0.22, cy - r * 0.22,
                              cx + r, cy, cx + r * 0.22, cy + r * 0.22,
                              cx, cy + r, cx - r * 0.22, cy + r * 0.22,
                              cx - r, cy, cx - r * 0.22, cy - r * 0.22,
                              fill=fill, outline="")
        except Exception:
            pass

    def _draw_app_mark(self, cv, cx, cy, s):
        """Large app mark for the chooser: dark editor window + orbit ring +
        glow dots/sparkles + carrot, on the page bg (no white box)."""
        x0, y0, x1, y1 = cx - s, cy - s * 0.72, cx + s, cy + s * 0.72
        try:
            cv.create_rectangle(x0, y0, x1, y1, fill="#14161d",
                                outline="#2b303d", width=2)
            gx = x0 + s * 0.16
            while gx < x1 - s * 0.06:
                cv.create_line(gx, y0 + s * 0.2, gx, y1 - s * 0.06, fill="#222836")
                gx += s * 0.2
            gy = y0 + s * 0.3
            while gy < y1 - s * 0.06:
                cv.create_line(x0 + s * 0.06, gy, x1 - s * 0.06, gy, fill="#222836")
                gy += s * 0.2
            for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
                cv.create_oval(x0 + s * (0.1 + i * 0.12) - 4, y0 + s * 0.06 - 4,
                               x0 + s * (0.1 + i * 0.12) + 4, y0 + s * 0.06 + 4,
                               fill=col, outline="")
            # back half of the orbit ring (behind carrot)
            cv.create_arc(x0 - s * 0.28, cy - s * 0.6, x1 + s * 0.28, cy + s * 0.6,
                          start=195, extent=150, outline="#ff8200",
                          width=max(3, int(s * 0.07)), style="arc")
            for dx, dy, r in ((-0.72, -0.1, 0.045), (0.78, -0.42, 0.045),
                              (0.62, 0.05, 0.035), (-0.5, 0.18, 0.035),
                              (0.85, 0.35, 0.05), (-0.42, 0.5, 0.045)):
                cv.create_oval(cx + s * dx - s * r, cy + s * dy - s * r,
                               cx + s * dx + s * r, cy + s * dy + s * r,
                               fill="#ffb300", outline="")
            self._sparkle(cv, cx - s * 0.62, cy - s * 0.3, s * 0.09)
            self._sparkle(cv, cx + s * 0.68, cy + s * 0.42, s * 0.075)
            # carrot on top
            self._draw_carrot(cv, cx, cy + s * 0.06, s * 0.44)
            # front half of the ring (over carrot base)
            cv.create_arc(x0 - s * 0.24, cy - s * 0.52, x1 + s * 0.24, cy + s * 0.52,
                          start=15, extent=150, outline="#ffc93c",
                          width=max(2, int(s * 0.045)), style="arc")
        except Exception:
            pass

    def _draw_carrot(self, cv, cx, cy, s):
        """Vector carrot logo (crisp at any size, no image file → no white box).
        Faceted orange body (dark left / bright right) + green spiky crown +
        black outlines + soft offset shadow, like the Carrot Studio artwork."""
        lw = max(2, int(s * 0.05))
        # soft drop shadow (stippled = fake translucency on dark bg)
        tx, ty = cx, cy - s * 0.30
        sh = (s * 0.07, s * 0.09)
        try:
            cv.create_polygon(tx + sh[0], ty + sh[1],
                              cx + s + sh[0], ty + s * 0.72 + sh[1],
                              cx + sh[0], ty + s * 2.35 + sh[1],
                              cx - s + sh[0], ty + s * 0.72 + sh[1],
                              fill="black", outline="", stipple="gray50")
        except Exception:
            pass
        # green spiky crown behind the body top
        ccx, ccy = cx, ty - s * 0.18
        R, r, spikes = s * 0.95, s * 0.60, 9
        pts = []
        for i in range(spikes * 2):
            a = -math.pi / 2 + i * math.pi / spikes
            rr = R if i % 2 == 0 else r
            pts += [ccx + math.cos(a) * rr, ccy + math.sin(a) * rr]
        try:
            cv.create_polygon(pts, fill="#00e436", outline="black", width=lw)
            # body halves: right bright, left dark
            cv.create_polygon(tx, ty, cx + s, ty + s * 0.72, cx, ty + s * 2.35,
                              fill="#ff8000", outline="")
            cv.create_polygon(tx, ty, cx, ty + s * 2.35, cx - s, ty + s * 0.72,
                              fill="#c25e00", outline="")
            # full outline
            cv.create_polygon(tx, ty, cx + s, ty + s * 0.72, cx, ty + s * 2.35,
                              cx - s, ty + s * 0.72,
                              fill="", outline="black", width=lw)
            # facet strokes on the dark half
            fw = max(1, int(s * 0.025))
            for x0, y0, x1, y1 in (
                    (-0.72, 0.98, -0.30, 0.80), (-0.66, 1.30, -0.28, 1.12),
                    (-0.55, 1.60, -0.24, 1.45)):
                cv.create_line(cx + s * x0, ty + s * y0, cx + s * x1, ty + s * y1,
                               fill="#8a3d00", width=fw)
        except Exception:
            pass

    def _show_chooser(self):
        """Startup page: pick 2D or 3D editor first, then open it directly."""
        self.chooser = tk.Frame(self, bg=CHOOSER_BG)
        self.chooser.pack(fill="both", expand=True)
        center = tk.Frame(self.chooser, bg=CHOOSER_BG)
        center.place(relx=0.5, rely=0.5, anchor="center")
        logo_cv = tk.Canvas(center, width=300, height=250, bg=CHOOSER_BG,
                            highlightthickness=0)
        logo_cv.pack()
        _png = self._logo_photo(280)
        if _png is not None:
            tk.Label(center, image=_png, bg=CHOOSER_BG).pack()
            logo_cv.destroy()
        else:
            self._draw_app_mark(logo_cv, 150, 122, 100)
        tk.Label(center, text="CARROT", fg="#ff7a00", bg=CHOOSER_BG,
                 font=("Segoe UI", 22, "bold")).pack(pady=(2, 0))
        tk.Label(center, text="PARTICLE EDITOR", fg="#00c853", bg=CHOOSER_BG,
                 font=("Segoe UI", 12, "bold")).pack(pady=(0, 2))
        tk.Label(center, text="ParticleFX — Choose your editor mode", fg=MUTED,
                 bg=CHOOSER_BG, font=FONT).pack(pady=(0, 18))
        cards = tk.Frame(center, bg=CHOOSER_BG)
        cards.pack()
        for mode, icon, title, desc in (
                ("2d", "▦", "2D", "Flat particle effects\nSprites & Simple SVG"),
                ("3d", "⬡", "3D", "Volumetric effects\nMeshes & Billboards")):
            card = tk.Frame(cards, bg=CHOOSER_CARD, width=210, height=200,
                            highlightthickness=1, highlightbackground=BORDER,
                            cursor="hand2")
            card.pack(side="left", padx=10)
            card.pack_propagate(False)
            tk.Label(card, text=icon, fg=TEXT, bg=CHOOSER_ICON_BG,
                     font=("Segoe UI", 26), width=3, pady=10).pack(pady=(22, 6))
            tk.Label(card, text=title, fg="white", bg=CHOOSER_CARD,
                     font=("Segoe UI", 13, "bold")).pack()
            tk.Label(card, text=desc, fg=MUTED, bg=CHOOSER_CARD,
                     font=FONT_SM, justify="center").pack(pady=(2, 0))

            def _open(m=mode):
                self._open_editor(m)

            def _hover_on(e, c=card):
                try:
                    c.configure(highlightbackground=ACCENT)
                except Exception:
                    pass

            def _hover_off(e, c=card):
                try:
                    c.configure(highlightbackground=BORDER)
                except Exception:
                    pass

            card.bind("<Button-1>", lambda e, m=mode: _open(m))
            card.bind("<Enter>", _hover_on)
            card.bind("<Leave>", _hover_off)
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, m=mode: _open(m))
                child.configure(cursor="hand2")
        tk.Label(center, text="دوس على الكارت أو اضغط 2 / 3", fg=MUTED,
                 bg=CHOOSER_BG, font=FONT_SM).pack(pady=(16, 0))

        def _key_open(mode):
            if getattr(self, "chooser", None) is None:
                return  # editor already open — never hijack typing in entries
            self._open_editor(mode)

        self.bind("<2>", lambda e: _key_open("2d"))
        self.bind("<3>", lambda e: _key_open("3d"))

    def _open_editor(self, ptype):
        """Destroy the chooser and build the real editor for the chosen mode."""
        if getattr(self, "_editor_built", False):
            self.set_type(ptype)
            return
        self._editor_built = True
        try:
            self.unbind("<2>")
            self.unbind("<3>")
        except Exception:
            pass
        if getattr(self, "chooser", None) is not None:
            self.chooser.destroy()
            self.chooser = None
        self.configure(bg=BG)
        self._build_topbar()
        self._build_main()
        self.set_type(ptype, commit=False)
        self._load_emitter_to_ui(default_emitter(ptype))
        self.refresh_states_ui()
        self._sim_reset()
        self._history_commit()  # baseline for undo
        self.bind_all("<Control-z>", lambda e: (self.undo(), "break")[1])
        self.bind_all("<Control-Z>", lambda e: (self.redo(), "break")[1])
        self.bind_all("<Control-Shift-z>", lambda e: (self.redo(), "break")[1])
        self.bind_all("<Control-Shift-Z>", lambda e: (self.redo(), "break")[1])
        self.bind_all("<Control-y>", lambda e: (self.redo(), "break")[1])
        self.bind_all("<Control-Y>", lambda e: (self.redo(), "break")[1])
        self.after(30, self._tick)
        if not getattr(self, "_preview_tab_opened", False):
            # starting editor → the WebGL viewport (PixiJS 2D / Three.js 3D)
            # is the main render engine: open it live-synced once settled
            self._preview_tab_opened = True
            self.after(600, self.open_fast_preview)

    # ================= top bar =================
    def _tbtn(self, parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd, relief="flat",
                      bg=ACCENT if accent else CARD, fg="white",
                      activebackground="#8f76ff" if accent else "#343646",
                      activeforeground="white", font=FONT_SM, padx=12, pady=5,
                      cursor="hand2", bd=0, highlightthickness=1,
                      highlightbackground=BORDER)
        b.pack(side="left", padx=3)
        return b

    def _build_topbar(self):
        bar = tk.Frame(self, bg="#23242f", height=46)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        _mini = self._logo_photo(24)
        if _mini is not None:
            tk.Label(bar, image=_mini, bg="#23242f").pack(side="left", padx=(10, 0))
        else:
            _logo = tk.Canvas(bar, width=26, height=26, bg="#23242f", highlightthickness=0)
            _logo.pack(side="left", padx=(10, 0))
            try:
                self._draw_carrot(_logo, 13, 12, 6.5)
            except Exception:
                pass
        tk.Label(bar, text="Carrot Studio", fg="#ff7a00", bg="#23242f", font=FONT_LOGO).pack(side="left", padx=(4, 0))
        self.e_filename = tk.Entry(bar, relief="flat", bg=INPUT, fg=TEXT, insertbackground="white",
                                   highlightthickness=1, highlightbackground=BORDER, width=16,
                                   font=FONT)
        self.e_filename.insert(0, self.filename)
        self.e_filename.pack(side="left", padx=12, ipady=4)
        # editor type segmented: 2D editor = 2D particles, 3D editor = 3D particles
        self.seg_type = tk.Frame(bar, bg="#23242f")
        self.seg_type.pack(side="left")
        self.type_btns = {}
        for t in ("2d", "3d"):
            b = tk.Button(self.seg_type, text=t.upper(), relief="flat", bd=0,
                          width=5, font=("Segoe UI", 9, "bold"), cursor="hand2",
                          command=lambda t=t: self.on_type_button(t))
            b.pack(side="left", padx=1)
            self.type_btns[t] = b
        # camera options (FOV + mouse sensitivity) — center of top bar
        camf = tk.Frame(bar, bg="#23242f")
        camf.pack(side="left", padx=24)
        tk.Label(camf, text="FOV", fg=MUTED, bg="#23242f", font=FONT_SM).pack(side="left")
        self.v_fov = tk.StringVar(value="60")
        tk.Entry(camf, textvariable=self.v_fov, relief="flat", bg=INPUT, fg=TEXT,
                 insertbackground="white", highlightthickness=1,
                 highlightbackground=BORDER, width=5, justify="center",
                 font=FONT_SM).pack(side="left", padx=(4, 12), ipady=4)
        tk.Label(camf, text=" الحساسية", fg=MUTED, bg="#23242f", font=FONT_SM).pack(side="left")
        self.v_sens = tk.StringVar(value="1.0")
        tk.Entry(camf, textvariable=self.v_sens, relief="flat", bg=INPUT, fg=TEXT,
                 insertbackground="white", highlightthickness=1,
                 highlightbackground=BORDER, width=5, justify="center",
                 font=FONT_SM).pack(side="left", padx=4, ipady=4)
        right = tk.Frame(bar, bg="#23242f")
        right.pack(side="right", padx=10)
        tk.Label(right, text="v0.2.0", fg=MUTED, bg="#23242f", font=FONT_SM).pack(side="left", padx=8)
        tk.Label(right, text="● DESKTOP", fg="white", bg=ACCENT, font=("Segoe UI", 8, "bold"),
                 padx=8, pady=3).pack(side="left")
        self._tbtn(right, "⟳ New", self.do_new)
        self._tbtn(right, "Save As", self.do_save_as)
        self._tbtn(right, "💾 Save", self.do_save)
        self._tbtn(right, "📁 Open", self.do_open)

    # ================= main split =================
    def _build_main(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)
        # --- sidebar (scrollable) ---
        side_wrap = tk.Frame(main, bg=SIDEBAR, width=290)
        side_wrap.pack(side="left", fill="y")
        side_wrap.pack_propagate(False)
        self.side_canvas = tk.Canvas(side_wrap, bg=SIDEBAR, highlightthickness=0)
        sb = tk.Scrollbar(side_wrap, orient="vertical", command=self.side_canvas.yview)
        self.side_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.side_canvas.pack(side="left", fill="both", expand=True)
        self.side = tk.Frame(self.side_canvas, bg=SIDEBAR)
        self.side_canvas.create_window((0, 0), window=self.side, anchor="nw", width=272)
        self.side.bind("<Configure>", lambda e: self.side_canvas.configure(scrollregion=self.side_canvas.bbox("all")))

        def _side_wheel(e):
            # scroll the sidebar with the wheel when hovering it (no need to grab the bar)
            w = str(e.widget)
            if w == str(self.side_canvas) or w.startswith(str(self.side)):
                self.side_canvas.yview_scroll(-1 if getattr(e, "delta", 0) > 0 else 1, "units")
                return "break"
            return None

        self.bind_all("<MouseWheel>", _side_wheel, add="+")
        self._build_sidebar()
        # --- viewport ---
        vp = tk.Frame(main, bg=BG)
        vp.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(vp, bg="#14151c", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        # --- orbit camera state (3D viewport) + 2D pan/gizmo offsets ---
        self.cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0, "ox": 0, "oy": 0, "focal": 620.0}
        # emitter world position (3D gizmo target)
        self.emitter_pos = [0.0, 0.0, 0.0]
        # 2D emitter offset in screen px (left-drag gizmo target)
        self.emitter2d = [0.0, 0.0]
        self._gizmo = None
        self.canvas.bind("<ButtonPress-1>", self._gizmo_down)
        self.canvas.bind("<B1-Motion>", self._gizmo_drag)
        self.canvas.bind("<ButtonRelease-1>", self._gizmo_up)
        self.canvas.bind("<Motion>", self._gizmo_hover)
        self.canvas.bind("<ButtonPress-3>", self._cam_down)
        self.canvas.bind("<B3-Motion>", self._cam_orbit)
        self.canvas.bind("<ButtonRelease-3>", self._drag_up)
        self.canvas.bind("<ButtonPress-2>", self._cam_down)
        self.canvas.bind("<B2-Motion>", self._cam_pan)
        self.canvas.bind("<ButtonRelease-2>", self._drag_up)
        self.canvas.bind("<MouseWheel>", self._cam_zoom)
        self.canvas.bind("<Double-Button-1>", lambda e: self._cam_reset())
        # stats card overlay
        self.stats = tk.Frame(vp, bg="#101116", highlightthickness=1, highlightbackground=BORDER)
        self.stats.place(relx=1.0, rely=0.0, x=-18, y=18, anchor="ne")
        self.l_particles = tk.Label(self.stats, text="Particles: 40", fg=TEXT, bg="#101116", font=FONT_SM)
        self.l_particles.pack(padx=10, pady=(6, 0), anchor="e")
        self.l_fps = tk.Label(self.stats, text="FPS: 60", fg=TEXT, bg="#101116", font=("Segoe UI", 9, "bold"))
        self.l_fps.pack(padx=10, pady=(0, 6), anchor="e")
        glow_row = tk.Frame(self.stats, bg="#101116")
        glow_row.pack(padx=10, pady=(0, 6), anchor="e")
        self.v_glow = tk.BooleanVar(value=True)
        self.b_glow = tk.Button(glow_row, text="✨ Glow: On", command=self._flip_glow,
                                bg=CARD, fg=TEXT, relief="flat", font=FONT_SM,
                                cursor="hand2", padx=6)
        self.b_glow.pack()
        self.v_gpu = tk.BooleanVar(value=True)
        self.b_gpu = tk.Button(glow_row, text="🎮 GPU: On", command=self._flip_gpu,
                               bg=CARD, fg=TEXT, relief="flat", font=FONT_SM,
                               cursor="hand2", padx=6)
        self.b_gpu.pack(pady=(4, 0))
        # hint pill
        self.hint = tk.Label(vp, text="",
                             fg=MUTED, bg="#101116", font=FONT_SM)
        self.hint.place(relx=0.5, rely=1.0, x=0, y=-16, anchor="s")
        self._update_hint()
        # bottom timeline strip
        strip = tk.Frame(vp, bg="#1e1f2a", height=64)
        strip.pack(fill="x", padx=10, pady=(0, 10))
        strip.pack_propagate(False)
        tk.Label(strip, text="STATES", fg=MUTED, bg="#1e1f2a", font=FONT_SEC).pack(side="left", padx=10)
        self.chip_row = tk.Frame(strip, bg="#1e1f2a")
        self.chip_row.pack(side="left", fill="x", expand=True)
        tk.Button(strip, text="+", command=lambda: self.add_state("intermediate"),
                  bg=CARD, fg=TEXT, relief="flat", width=3, cursor="hand2").pack(side="right", padx=4)
        tk.Button(strip, text="🚀 معاينة سريعة 60FPS", command=self.open_fast_preview,
                  bg=ACCENT, fg="white", relief="flat", font=FONT_SM,
                  cursor="hand2", padx=8).pack(side="right", padx=4)
        self.status = tk.Label(strip, text="جاهز", fg=OK, bg="#1e1f2a", font=FONT_SM)
        self.status.pack(side="right", padx=10)

    # ================= sidebar widgets =================
    def _sec(self, title):
        tk.Label(self.side, text=f"▾   ⚡  {title}" if title == "Emitter" else title,
                 fg=TEXT if title == "Emitter" else MUTED, bg=SIDEBAR,
                 font=("Segoe UI", 10, "bold") if title == "Emitter" else FONT_SEC,
                 anchor="w").pack(fill="x", padx=12, pady=(12, 2))

    def _sub(self, title):
        f = tk.Frame(self.side, bg=SIDEBAR)
        f.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(f, text=title, fg=MUTED, bg=SIDEBAR, font=FONT_SEC).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=6, pady=5)
        return f

    def _row(self, label, icon=""):
        f = tk.Frame(self.side, bg=SIDEBAR)
        f.pack(fill="x", padx=12, pady=3)
        tk.Label(f, text=f"{icon}  {label}" if icon else label, fg=MUTED, bg=SIDEBAR,
                 font=FONT, width=13, anchor="w").pack(side="left")
        return f

    def _num(self, parent, var, width=12):
        e = tk.Entry(parent, textvariable=var, relief="flat", bg=INPUT, fg=TEXT,
                     insertbackground="white", highlightthickness=1,
                     highlightbackground=BORDER, width=width, justify="center", font=FONT)
        e.pack(side="left", ipady=5)
        return e

    def _combo(self, parent, var, values, width=12):
        c = tk.OptionMenu(parent, var, *values)
        c.configure(bg=INPUT, fg=TEXT, relief="flat", highlightthickness=1,
                    highlightbackground=BORDER, activebackground=CARD, bd=0, width=width - 2,
                    font=FONT, cursor="hand2")
        c["menu"].configure(bg=CARD, fg=TEXT, relief="flat", font=FONT)
        c.pack(side="left", ipady=2)
        return c

    def _toggle(self, parent, var, cb=None):
        b = tk.Button(parent, relief="flat", bd=0, width=6, font=("Segoe UI", 9, "bold"),
                      cursor="hand2")
        def render():
            on = bool(var.get())
            b.configure(text="On" if on else "Off",
                        bg=ACCENT if on else "#3a3b4a", fg="white")
        def flip():
            var.set(not var.get())
            render()
            if cb:
                cb()
        b.configure(command=flip)
        b.pack(side="left")
        render()
        b._render = render
        return b

    def _segmented(self, parent, var, options):
        f = tk.Frame(parent, bg=SIDEBAR)
        f.pack(side="left")
        btns = []
        def render():
            for b, v in btns:
                on = (var.get() == v)
                b.configure(bg=ACCENT if on else "#3a3b4a", fg="white")
        for v in options:
            b = tk.Button(f, text=v, relief="flat", bd=0, width=8, font=FONT_SM,
                          bg="#3a3b4a", fg="white", cursor="hand2")
            b.pack(side="left", padx=1)
            btns.append((b, v))
            b.configure(command=lambda v=v: (var.set(v), render()))
        render()
        return f

    def _build_sidebar(self):
        self._sec("Emitter")
        self._sub("PARTICLE OUTPUT")
        self.v_flow = tk.StringVar(value="40")
        self.v_max = tk.StringVar(value="300")
        self.v_mode = tk.StringVar(value="Infinite")
        self.v_reverse = tk.BooleanVar(value=False)
        self.v_align = tk.BooleanVar(value=True)
        r = self._row("Flow", "⟳"); self._num(r, self.v_flow); tk.Label(r, text="", bg=SIDEBAR).pack(side="left")
        r = self._row("Max particles", "▤"); self._num(r, self.v_max)
        r = self._row("Mode"); self._combo(r, self.v_mode, MODES)
        r = self._row("Reverse", "⇄"); self._toggle(r, self.v_reverse)
        r = self._row("Align dir.", "➤"); self.t_align = self._toggle(r, self.v_align)

        self._sub("GRAVITY")
        self.v_gx = tk.StringVar(value="0"); self.v_gy = tk.StringVar(value="0"); self.v_gz = tk.StringVar(value="0")
        r = self._row("Gravity X", "→"); self._num(r, self.v_gx)
        r = self._row("Gravity Y", "↓"); self._num(r, self.v_gy)
        r = self._row("Gravity Z", "↕"); self._num(r, self.v_gz)
        self.row_gz = r  # 3D-only

        self.anchor_zone = self._sub("EMISSION ZONE")
        self.v_zshape = tk.StringVar(value="Sphere")
        self.v_rot = tk.StringVar(value="0")
        self.v_radius = tk.StringVar(value="10")
        self.v_zonemode = tk.StringVar(value="Surface")
        self.v_showzone = tk.BooleanVar(value=True)
        r = self._row("Shape", "○"); self.cb_shape = self._combo(r, self.v_zshape, ZONE_3D)
        r = self._row("Rotation", "⟳"); self._num(r, self.v_rot); tk.Label(r, text="°", fg=MUTED, bg=SIDEBAR).pack(side="left")
        r = self._row("Radius", "↔"); self._num(r, self.v_radius); tk.Label(r, text="px", fg=MUTED, bg=SIDEBAR).pack(side="left", padx=4)
        self.v_width = tk.StringVar(value="100"); self.v_height = tk.StringVar(value="60")
        self.v_length = tk.StringVar(value="100"); self.v_depth = tk.StringVar(value="60")
        r = self._row("Width", "↔"); self._num(r, self.v_width)
        r = self._row("Height", "↕"); self._num(r, self.v_height)
        r = self._row("Length", "↔"); self._num(r, self.v_length)
        r = self._row("Depth", "↕"); self._num(r, self.v_depth)
        self.row_depth = r  # 3D-only
        r = self._row("Mode", "◉"); self._segmented(r, self.v_zonemode, ZONE_MODE)
        self.row_zonemode = r
        r = self._row("Show zone", "👁"); self._toggle(r, self.v_showzone)

        self._sub("PROPAGATION CONE")
        self.v_dirz = tk.StringVar(value="0"); self.v_diry = tk.StringVar(value="0")
        self.v_spread = tk.StringVar(value="90")
        self.v_showcone = tk.BooleanVar(value=True)
        r = self._row("Dir. Z", "⟳"); self._num(r, self.v_dirz); tk.Label(r, text="°", fg=MUTED, bg=SIDEBAR).pack(side="left")
        self.row_dirz = r; self.lbl_dirz = r.winfo_children()[0]
        r = self._row("Dir. Y", "⟳"); self._num(r, self.v_diry); tk.Label(r, text="°", fg=MUTED, bg=SIDEBAR).pack(side="left")
        self.row_diry = r  # 3D-only
        r = self._row("Spread", "⤢"); self._num(r, self.v_spread); tk.Label(r, text="°", fg=MUTED, bg=SIDEBAR).pack(side="left")
        self.row_spread = r
        r = self._row("Show cone", "👁"); self._toggle(r, self.v_showcone)

        self._sub("STATES")
        self.state_form = tk.Frame(self.side, bg=SIDEBAR)
        self.state_form.pack(fill="x", padx=12, pady=4)
        self.s_label = tk.StringVar(value="birth"); self.s_role = tk.StringVar(value="birth")
        self.s_dur = tk.StringVar(value="0.5"); self.s_shape = tk.StringVar(value="sphere")
        self.s_ease = tk.StringVar(value="linear")
        self.s_size = tk.StringVar(value="8"); self.s_sizemax = tk.StringVar(value="12")
        self.s_color = tk.StringVar(value="#ffffff"); self.s_op = tk.StringVar(value="255")
        self.s_mins = tk.StringVar(value="60"); self.s_maxs = tk.StringVar(value="160")
        # preview color mode: selected-state color (WYSIWYG) or full gradient
        self.v_colormode = tk.StringVar(value="متدرج")
        fcm = tk.Frame(self.state_form, bg=SIDEBAR); fcm.pack(fill="x", pady=2)
        tk.Label(fcm, text="لون المعاينة", fg=MUTED, bg=SIDEBAR, font=FONT_SM, width=11, anchor="w").pack(side="left")
        self._segmented(fcm, self.v_colormode, ["المحدد", "متدرج"])

        def srow(lbl, var, vals=None):
            f = tk.Frame(self.state_form, bg=SIDEBAR)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=lbl, fg=MUTED, bg=SIDEBAR, font=FONT_SM, width=11, anchor="w").pack(side="left")
            if vals:
                c = tk.OptionMenu(f, var, *vals)
                c.configure(bg=INPUT, fg=TEXT, relief="flat", bd=0, width=10, font=FONT_SM)
                c["menu"].configure(bg=CARD, fg=TEXT, font=FONT_SM)
                c.pack(side="left")
                return c
            tk.Entry(f, textvariable=var, relief="flat", bg=INPUT, fg=TEXT,
                     insertbackground="white", highlightthickness=1,
                     highlightbackground=BORDER, width=12, justify="center",
                     font=FONT_SM).pack(side="left", ipady=4)
            return f
        srow("Label", self.s_label); srow("Duration", self.s_dur)
        self.om_shape = srow("Shape", self.s_shape, SHAPES_2D)
        srow("Easing", self.s_ease, EASINGS)
        srow("Size", self.s_size); srow("SizeMax", self.s_sizemax)
        f = tk.Frame(self.state_form, bg=SIDEBAR); f.pack(fill="x", pady=2)
        tk.Label(f, text="Color", fg=MUTED, bg=SIDEBAR, font=FONT_SM, width=11, anchor="w").pack(side="left")
        self.color_swatch = tk.Button(f, text="  ", command=self.pick_color, relief="flat",
                                      bg="#ffffff", width=4, cursor="hand2")
        self.color_swatch.pack(side="left", padx=(0, 4))
        tk.Entry(f, textvariable=self.s_color, relief="flat", bg=INPUT, fg=TEXT, width=10,
                 justify="center", font=FONT_SM).pack(side="left", ipady=4)
        srow("Opacity", self.s_op); srow("MinSpeed", self.s_mins); srow("MaxSpd", self.s_maxs)
        brow = tk.Frame(self.state_form, bg=SIDEBAR); brow.pack(pady=6)
        tk.Button(brow, text="حفظ", command=self.save_state, bg=ACCENT, fg="white",
                  relief="flat", width=8, cursor="hand2").pack(side="left", padx=2)
        tk.Button(brow, text="حذف", command=self.del_state, bg="#3a3b4a", fg="white",
                  relief="flat", width=8, cursor="hand2").pack(side="left", padx=2)
        # --- custom shape model upload (visible only when Shape == custom) ---
        self.s_custom_file = tk.StringVar(value="")
        self.s_node = tk.StringVar(value="")
        self._custom_nodes = []
        self.row_custom = tk.Frame(self.state_form, bg=SIDEBAR)
        self.btn_upload = tk.Button(self.row_custom, text="📦 Upload 3D",
                                    command=self.upload_custom_model,
                                    bg=CARD, fg=TEXT, relief="flat",
                                    font=FONT_SM, cursor="hand2", padx=6, pady=4)
        self.btn_upload.pack(side="left", padx=2)
        self.lbl_custom_file = tk.Label(self.row_custom, text="مفيش ملف",
                                        fg=MUTED, bg=SIDEBAR, font=FONT_SM)
        self.lbl_custom_file.pack(side="left", padx=4)
        tk.Button(self.row_custom, text="✕", command=self.clear_custom_model,
                  bg="#3a3b4a", fg=TEXT, relief="flat", width=3,
                  cursor="hand2").pack(side="left", padx=2)
        self.row_custom_node = tk.Frame(self.state_form, bg=SIDEBAR)
        tk.Label(self.row_custom_node, text="Node", fg=MUTED, bg=SIDEBAR,
                 font=FONT_SM, width=11, anchor="w").pack(side="left")
        self.om_node = tk.OptionMenu(self.row_custom_node, self.s_node, "")
        self.om_node.configure(bg=INPUT, fg=TEXT, relief="flat", bd=0,
                               width=10, font=FONT_SM)
        self.om_node["menu"].configure(bg=CARD, fg=TEXT, font=FONT_SM)
        self.om_node.pack(side="left")
        self.lbl_custom_hint = tk.Label(self.state_form, fg=MUTED, bg=SIDEBAR,
                                        font=FONT_SM, wraplength=240,
                                        justify="left", anchor="w")
        self.s_shape.trace_add("write", lambda *a: self._update_custom_row())

        self._sub("TEMPLATES")
        trow = tk.Frame(self.side, bg=SIDEBAR); trow.pack(padx=12, pady=4)
        for name in TEMPLATES:
            tk.Button(trow, text=name, command=lambda n=name: self.apply_template(n),
                      bg=CARD, fg=TEXT, relief="flat", font=FONT_SM, cursor="hand2",
                      padx=8, pady=4).pack(side="left", padx=2)

        tk.Button(self.side, text="⬇  تصدير JSON", command=self.do_save_as,
                  bg=ACCENT, fg="white", relief="flat", font=("Segoe UI", 11, "bold"),
                  cursor="hand2", pady=6).pack(fill="x", padx=12, pady=14)
        self._watch_realtime()

    # ================= data <-> ui =================
    def toggle_type(self):
        self.on_type_button("2d" if self.ptype == "3d" else "3d")

    def on_type_button(self, t):
        """Editor switch from the 2D|3D segmented control.
        First entry into an editor auto-opens the main WebGL viewport once
        (PixiJS for 2D, Three.js for 3D, same live-synced tab); the in-app
        canvas stays as the edit/gizmo view."""
        first = (self.ptype != t)
        self.set_type(t)
        if first and not getattr(self, "_preview_tab_opened", False):
            self._preview_tab_opened = True
            self.open_fast_preview()

    def set_type(self, t, commit=True):
        """Switch editor: 2D editor edits 2D particles, 3D editor edits 3D particles."""
        self.ptype = t
        for k, b in getattr(self, "type_btns", {}).items():
            b.configure(bg=ACCENT if k == t else "#3a3b4a", fg="white")
        shapes = ZONE_2D if t == "2d" else ZONE_3D
        menu = self.cb_shape["menu"]
        menu.delete(0, "end")
        for s in shapes:
            menu.add_command(label=s, command=lambda v=s: self.v_zshape.set(v))
        self.v_zshape.set(shapes[0])
        # particle Shape menu: 2D shapes in 2D editor, 3D solids (+flats) in 3D editor
        pshapes = SHAPES_2D if t == "2d" else SHAPES_3D
        smenu = self.om_shape["menu"]
        smenu.delete(0, "end")
        for s in pshapes:
            smenu.add_command(label=s, command=lambda v=s: self.s_shape.set(v))
        if self.s_shape.get() not in pshapes:
            self.s_shape.set(pshapes[0])
        # 3D-only rows visible in 3D editor only; 2D rows always visible
        for row, anchor in ((getattr(self, "row_gz", None), getattr(self, "anchor_zone", None)),
                            (getattr(self, "row_diry", None), getattr(self, "row_spread", None)),
                            (getattr(self, "row_depth", None), getattr(self, "row_zonemode", None))):
            if row is None:
                continue
            if t == "3d":
                if anchor is not None:
                    row.pack(fill="x", padx=12, pady=3, before=anchor)
                else:
                    row.pack(fill="x", padx=12, pady=3)
            else:
                row.pack_forget()
        if getattr(self, "lbl_dirz", None) is not None:
            self.lbl_dirz.configure(text="➤  Direction" if t == "2d" else "⟳  Dir. Z")
        self._update_hint()
        if hasattr(self, "row_custom"):
            self._update_custom_row()
        self._sim_reset()
        if commit:
            self._history_commit()

    def _watch_realtime(self):
        """Every field edit marks the cached effect dirty → viewport updates live.
        Document edits additionally schedule a debounced undo-history commit."""
        doc_vars = ("v_flow", "v_max", "v_mode", "v_reverse", "v_align",
                    "v_gx", "v_gy", "v_gz", "v_zshape", "v_rot", "v_radius",
                    "v_width", "v_height", "v_length", "v_depth", "v_zonemode",
                    "v_showzone", "v_dirz", "v_diry", "v_spread", "v_showcone")
        for name in doc_vars:
            var = getattr(self, name, None)
            if var is not None:
                var.trace_add("write", self._on_doc_changed)
        # preview-only (no history): sensitivity / color mode
        for name in ("v_colormode", "v_sens"):
            var = getattr(self, name, None)
            if var is not None:
                var.trace_add("write", lambda *a: self._mark_dirty())
        # FOV is part of the camera gizmo → undoable
        if getattr(self, "v_fov", None) is not None:
            self.v_fov.trace_add("write", self._on_doc_changed)
        # state fields: persist into the selected state live (like settings)
        for name in ("s_label", "s_dur", "s_shape", "s_ease", "s_size",
                     "s_sizemax", "s_color", "s_op", "s_mins", "s_maxs",
                     "s_node"):
            var = getattr(self, name, None)
            if var is not None:
                var.trace_add("write", self._on_state_field)

    def _on_doc_changed(self, *a):
        self._mark_dirty()
        if getattr(self, "_restoring", False):
            return
        if self._debounce_after is not None:
            try:
                self.after_cancel(self._debounce_after)
            except Exception:
                pass
        self._debounce_after = self.after(800, self._debounce_commit)

    def _on_state_field(self, *a):
        if getattr(self, "_restoring", False) or getattr(self, "_loading", False):
            return
        self._persist_form(silent=True)
        self._on_doc_changed()

    def _debounce_commit(self):
        self._debounce_after = None
        if getattr(self, "_restoring", False):
            return
        self._history_commit()

    # ================= undo / redo (Ctrl+Z / Ctrl+Shift+Z) =================
    def _snapshot(self):
        em = self._read_emitter(silent=True)
        if em is None:
            return None
        return {"ptype": self.ptype,
                "filename": self.e_filename.get(),
                "emitter": em,
                "states": copy.deepcopy(self.states),
                "sel": self.sel_state,
                "cam": {k: self.cam[k] for k in ("yaw", "pitch", "zoom", "ox", "oy")},
                "emitter_pos": list(getattr(self, "emitter_pos", (0.0, 0.0, 0.0))),
                "emitter2d": list(getattr(self, "emitter2d", (0.0, 0.0))),
                "fov": getattr(self, "v_fov", None).get() if getattr(self, "v_fov", None) is not None else "60"}

    def _history_commit(self):
        if getattr(self, "_restoring", False):
            return
        if self._debounce_after is not None:
            try:
                self.after_cancel(self._debounce_after)
            except Exception:
                pass
            self._debounce_after = None
        snap = self._snapshot()
        if snap is None:
            return
        key = json.dumps(snap, sort_keys=True, ensure_ascii=False)
        if self._history and self._history[self._hidx][0] == key:
            return  # unchanged — no duplicate entry
        del self._history[self._hidx + 1:]
        self._history.append((key, snap))
        if len(self._history) > 100:
            self._history.pop(0)
        self._hidx = len(self._history) - 1

    def _history_restore(self, snap):
        if self._debounce_after is not None:
            try:
                self.after_cancel(self._debounce_after)
            except Exception:
                pass
            self._debounce_after = None
        self._restoring = True
        try:
            self.set_type(snap["ptype"], commit=False)
            self._load_emitter_to_ui(snap["emitter"])
            self.states = copy.deepcopy(snap["states"])
            self.sel_state = max(0, min(snap.get("sel", 0), len(self.states) - 1))
            self.e_filename.delete(0, "end")
            self.e_filename.insert(0, snap.get("filename", "Default"))
            self.cam.update(snap.get("cam", {}))
            self.emitter_pos = list(snap.get("emitter_pos", (0.0, 0.0, 0.0)))
            self.emitter2d = list(snap.get("emitter2d", (0.0, 0.0)))
            if getattr(self, "v_fov", None) is not None:
                self.v_fov.set(snap.get("fov", "60"))
            self.refresh_states_ui()
            self._sim_reset()
        finally:
            self._restoring = False

    def undo(self):
        self._history_commit()  # flush pending typing first
        if self._hidx > 0:
            self._hidx -= 1
            self._history_restore(self._history[self._hidx][1])
            self.status.configure(text="↩ تراجع", fg=MUTED)

    def redo(self):
        if self._hidx < len(self._history) - 1:
            self._hidx += 1
            self._history_restore(self._history[self._hidx][1])
            self.status.configure(text="↪ إعادة", fg=MUTED)

    # ================= orbit camera (3D viewport) =================
    def _update_hint(self):
        if getattr(self, "ptype", "2d") == "3d":
            self.hint.configure(text="3D — العرض الأساسي Three.js WebGL | هنا: تدوير يمين+سحب، الجيزمو شمال+سحب، الوسط تحريك، سكرول زوم، دبل كليك reset")
        else:
            self.hint.configure(text="2D — العرض الأساسي PixiJS WebGL | هنا: الجيزمو شمال+سحب (X/Y)، الوسط تحريك، سكرول زوم، دبل كليك reset")

    def _view_center(self):
        c = self.canvas
        return (max(100, c.winfo_width()) * 0.5, max(100, c.winfo_height()) * 0.52)

    @staticmethod
    def _pt_seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        n = dx * dx + dy * dy
        t = 0.0 if n < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / n))
        return math.hypot(px - (ax + dx * t), py - (ay + dy * t))

    def _gizmo_screen(self):
        """Project emitter origin + XYZ axis tips. Returns (o, tips)."""
        cx, cy = self._view_center()
        ex, ey, ez = self.emitter_pos
        o = self._proj(ex, ey, ez, cx, cy)[:2]
        tips = []
        for ax, ay, az in ((70, 0, 0), (0, 70, 0), (0, 0, 70)):
            tips.append(self._proj(ex + ax, ey + ay, ez + az, cx, cy)[:2])
        return o, tips

    def _gizmo_hit(self, e):
        """Left-click target: 3D → 'move' | ('axis', i); 2D → 'move2d'; else None."""
        cx, cy = self._view_center()
        if self.ptype == "3d":
            o, tips = self._gizmo_screen()
            if math.hypot(e.x - o[0], e.y - o[1]) <= 14:
                return "move"
            for i, t in enumerate(tips):
                if self._pt_seg_dist(e.x, e.y, o[0], o[1], t[0], t[1]) <= 10:
                    return ("axis", i)
            return None
        ex, ey = cx + self.cam["ox"] + self.emitter2d[0], cy + self.cam["oy"] + self.emitter2d[1]
        if math.hypot(e.x - ex, e.y - ey) <= 14:
            return "move2d"
        return None

    def _gizmo_down(self, e):
        hit = self._gizmo_hit(e)
        self._gizmo = None if hit is None else {"kind": hit, "x": e.x, "y": e.y}

    def _gizmo_up(self, e):
        if self._gizmo is not None:
            self._gizmo = None
            self._history_commit()  # gizmo move = one undo step

    def _drag_up(self, e):
        # orbit/pan release (right/middle button) = one undo step
        if getattr(self, "_drag", None) is not None:
            self._drag = None
            self._history_commit()

    def _gizmo_hover(self, e):
        if self._gizmo is not None or getattr(e, "state", 0) & 0x100:
            return
        try:
            hit = self._gizmo_hit(e)
            self.canvas.configure(cursor="fleur" if hit == "move" else ("hand2" if hit else ""))
        except Exception:
            pass

    def _cam_basis(self):
        """Camera right/up world vectors + origin scale for gizmo dragging."""
        syaw, cyaw = math.sin(self.cam["yaw"]), math.cos(self.cam["yaw"])
        spit, cpit = math.sin(self.cam["pitch"]), math.cos(self.cam["pitch"])
        right = (cyaw, 0.0, syaw)
        up = (spit * syaw, cpit, -spit * cyaw)
        cx, cy = self._view_center()
        sc = self._proj(*self.emitter_pos, cx, cy)[2]
        return right, up, max(1e-6, sc)

    def _gizmo_drag(self, e):
        g = self._gizmo
        if g is None:
            return
        dx, dy = e.x - g["x"], e.y - g["y"]
        g["x"], g["y"] = e.x, e.y
        if g["kind"] == "move2d":
            self.emitter2d[0] += dx
            self.emitter2d[1] += dy
            return
        if self.ptype != "3d":
            return
        right, up, sc = self._cam_basis()
        if g["kind"] == "move":
            # free move in camera plane
            self.emitter_pos[0] += (dx * right[0] - dy * up[0]) / sc
            self.emitter_pos[1] += (dx * right[1] - dy * up[1]) / sc
            self.emitter_pos[2] += (dx * right[2] - dy * up[2]) / sc
        else:
            # axis-constrained: project pixel delta onto the axis screen dir
            i = g["kind"][1]
            o, tips = self._gizmo_screen()
            ax, ay = tips[i][0] - o[0], tips[i][1] - o[1]
            n = math.hypot(ax, ay)
            if n < 1e-6:
                return
            along = (dx * ax + dy * ay) / n / sc
            unit = ((1, 0, 0), (0, 1, 0), (0, 0, 1))[i]
            self.emitter_pos[0] += unit[0] * along
            self.emitter_pos[1] += unit[1] * along
            self.emitter_pos[2] += unit[2] * along

    def _cam_down(self, e):
        self._drag = (e.x, e.y)

    def _cam_reset(self):
        self.cam.update({"yaw": 0.7, "pitch": 0.42, "zoom": 1.0, "ox": 0, "oy": 0})
        self.emitter_pos = [0.0, 0.0, 0.0]
        self.emitter2d = [0.0, 0.0]

    def _get_fov(self):
        try:
            return max(10.0, min(120.0, float(self.v_fov.get())))
        except (ValueError, TypeError, AttributeError):
            return 60.0

    def _get_sens(self):
        try:
            return max(0.1, min(5.0, float(self.v_sens.get())))
        except (ValueError, TypeError, AttributeError):
            return 1.0

    def _cam_orbit(self, e):
        if self.ptype != "3d" or self._drag is None:
            return
        s = self._get_sens()
        dx, dy = e.x - self._drag[0], e.y - self._drag[1]
        self._drag = (e.x, e.y)
        self.cam["yaw"] += dx * 0.01 * s
        self.cam["pitch"] = max(-1.4, min(1.4, self.cam["pitch"] + dy * 0.01 * s))

    def _cam_pan(self, e):
        if self._drag is None:
            return
        s = self._get_sens()
        dx, dy = e.x - self._drag[0], e.y - self._drag[1]
        self._drag = (e.x, e.y)
        self.cam["ox"] += dx * s
        self.cam["oy"] += dy * s

    def _cam_zoom(self, e):
        s = self._get_sens()
        f = 1.12 if getattr(e, "delta", 0) > 0 else 1 / 1.12
        self.cam["zoom"] = max(0.3, min(4.0, self.cam["zoom"] * (f ** s)))
        self._on_doc_changed()  # debounced undo step

    def _proj(self, x, y, z, cx, cy):
        """World (x right, y up, z toward viewer) -> screen. Returns (sx, sy, scale, depth)."""
        syaw, cyaw = math.sin(self.cam["yaw"]), math.cos(self.cam["yaw"])
        spit, cpit = math.sin(self.cam["pitch"]), math.cos(self.cam["pitch"])
        x1 = x * cyaw + z * syaw
        z1 = -x * syaw + z * cyaw
        y2 = y * cpit - z1 * spit
        z2 = y * spit + z1 * cpit
        f = self.cam.get("focal", 620.0)
        scale = self.cam["zoom"] * f / (f + z2)
        return (cx + self.cam["ox"] + x1 * scale, cy + self.cam["oy"] - y2 * scale, scale, z2)

    @staticmethod
    def _cone_dir3(bx, by, bz, spread_deg):
        """Random unit vector inside a cone around base dir (bx,by,bz)."""
        n = math.sqrt(bx * bx + by * by + bz * bz) or 1.0
        bx, by, bz = bx / n, by / n, bz / n
        # orthonormal basis
        ux, uy, uz = (0.0, 1.0, 0.0) if abs(by) < 0.95 else (1.0, 0.0, 0.0)
        # u = norm(cross(b, up))
        cx1, cy1, cz1 = by * uz - bz * uy, bz * ux - bx * uz, bx * uy - by * ux
        n1 = math.sqrt(cx1 * cx1 + cy1 * cy1 + cz1 * cz1) or 1.0
        ux, uy, uz = cx1 / n1, cy1 / n1, cz1 / n1
        # v = cross(b, u)
        vx, vy, vz = by * uz - bz * uy, bz * ux - bx * uz, bx * uy - by * ux
        a = random.random() * math.pi * 2
        r = math.tan(math.radians(spread_deg / 2)) * math.sqrt(random.random())
        dx, dy, dz = bx + (ux * math.cos(a) + vx * math.sin(a)) * r, \
                     by + (uy * math.cos(a) + vy * math.sin(a)) * r, \
                     bz + (uz * math.cos(a) + vz * math.sin(a)) * r
        n2 = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        return (dx / n2, dy / n2, dz / n2)

    def _load_emitter_to_ui(self, em):
        # Tk has no blend widget (see DPG sidebar): stash the loaded value so
        # save round-trips preserve it instead of resetting to Normal.
        bm = em.get("blendingMode")
        self._em_blending = bm if bm in BLEND_MODES else "Normal"
        self.v_flow.set(str(em.get("flow", 40)))
        self.v_max.set(str(em.get("maxParticles", 300)))
        self.v_mode.set(em.get("mode", "Infinite"))
        self.v_reverse.set(bool(em.get("reverse", False)))
        self.v_align.set(bool(em.get("alignDir", False)))
        g = em.get("gravity", {})
        self.v_gx.set(str(g.get("x", 0))); self.v_gy.set(str(g.get("y", 0))); self.v_gz.set(str(g.get("z", 0)))
        z = em.get("emissionZone", {})
        self.v_zshape.set(str(z.get("shape", "Sphere")))
        self.v_rot.set(str(z.get("rotation", z.get("rotationZ", 0))))
        self.v_radius.set(str(z.get("radius", 10)))
        self.v_width.set(str(z.get("width", 100))); self.v_height.set(str(z.get("height", 60)))
        self.v_length.set(str(z.get("length", 100))); self.v_depth.set(str(z.get("depth", 60)))
        self.v_zonemode.set(str(z.get("mode", "Surface")))
        self.v_showzone.set(bool(z.get("showZone", True)))
        c = em.get("propagationCone", {})
        self.v_dirz.set(str(c.get("directionZ", c.get("direction", 0))))
        self.v_diry.set(str(c.get("directionY", 0)))
        self.v_spread.set(str(c.get("spread", 90)))
        self.v_showcone.set(bool(c.get("showCone", True)))

    def _read_emitter(self, silent=False):
        try:
            f = lambda v: float(v.get())
            # strict editor separation: a 2D shape can never leak into a 3D file and vice versa
            zraw = self.v_zshape.get()
            if self.ptype == "3d":
                zshape = zraw.lower() if zraw.lower() in ZONE_3D else "sphere"
                return {
                    "flow": f(self.v_flow), "flowMode": "rate", "flowInterval": 1,
                    "maxParticles": int(f(self.v_max)), "reservoir": int(f(self.v_max)),
                    "mode": self.v_mode.get(), "reverse": bool(self.v_reverse.get()),
                    "alignDir": bool(self.v_align.get()), "billboard": True,
                    "rotationMode": "speed",
                    "gravity": {"x": f(self.v_gx), "y": f(self.v_gy), "z": f(self.v_gz)},
                    "emissionZone": {"shape": zshape,
                                     "radius": f(self.v_radius), "width": f(self.v_width),
                                     "height": f(self.v_height), "depth": f(self.v_depth),
                                     "length": f(self.v_length), "mode": self.v_zonemode.get(),
                                     "rotationX": 0, "rotationY": 0, "rotationZ": f(self.v_rot),
                                     "showZone": bool(self.v_showzone.get())},
                    "propagationCone": {"directionX": 0, "directionY": f(self.v_diry),
                                        "directionZ": f(self.v_dirz),
                                        "spread": f(self.v_spread),
                                        "showCone": bool(self.v_showcone.get())},
                    "blendingMode": getattr(self, "_em_blending", "Normal"),
                }
            zshape2 = zraw if zraw in ZONE_2D else "Circle"
            return {
                "flow": f(self.v_flow), "flowMode": "rate", "flowInterval": 1,
                "maxParticles": int(f(self.v_max)), "reservoir": int(f(self.v_max)),
                "mode": self.v_mode.get(), "reverse": bool(self.v_reverse.get()),
                "alignDir": bool(self.v_align.get()), "rotationMode": "speed",
                "gravity": {"x": f(self.v_gx), "y": f(self.v_gy)},
                "emissionZone": {"shape": zshape2, "rotation": f(self.v_rot),
                                 "radius": f(self.v_radius), "width": f(self.v_width),
                                 "height": f(self.v_height), "length": f(self.v_length),
                                 "mode": self.v_zonemode.get(),
                                 "showZone": bool(self.v_showzone.get())},
                "propagationCone": {"direction": f(self.v_dirz),
                                    "spread": f(self.v_spread),
                                    "showCone": bool(self.v_showcone.get())},
                "blendingMode": getattr(self, "_em_blending", "Normal"),
            }
        except ValueError:
            if not silent:
                messagebox.showerror("خطأ", "قيمة رقمية غلط")
            return None

    def current_effect(self, silent=False):
        em = self._read_emitter(silent=silent)
        if em is None:
            return None
        states = []
        for s in self.states:
            ns = json.loads(json.dumps(s))
            # strict editor separation for particle shapes too
            shp = str(ns.get("shape", "") or "").lower()
            if self.ptype == "3d":
                ns["shape"] = shp if shp in SHAPES_3D else "sphere"
                mv = ns.get("movement", {})
                zmin = mv.get("minRot", mv.get("minRotZ", 0))
                zmax = mv.get("maxRot", mv.get("maxRotZ", 0))
                mv.update({"minRotX": 0, "maxRotX": 0, "minRotY": 0, "maxRotY": 0,
                           "minRotZ": zmin, "maxRotZ": zmax})
                mv.pop("minRot", None); mv.pop("maxRot", None)
                ns["movement"] = mv
            else:
                ns["shape"] = shp if shp in SHAPES_2D else "circle"
            ns.pop("customModel", None)  # studio-only UI memory, not runtime data
            states.append(ns)
        eff = build_effect(self.ptype, em, states)
        if self.ptype == "3d":
            block = effect_models_block(self.states, states)
            if block is not None:
                eff["models"] = block
        return eff

    # ---- states ----
    def refresh_states_ui(self):
        for w in self.chip_row.winfo_children():
            w.destroy()
        for i, s in enumerate(self.states):
            col = s.get("appearance", {}).get("color", "#fff")
            sel = (i == self.sel_state)
            b = tk.Button(self.chip_row, text=f"● {s.get('label')}",
                          bg=ACCENT if sel else CARD, fg="white" if sel else TEXT,
                          relief="flat", font=FONT_SM, padx=10, pady=6, cursor="hand2",
                          command=lambda i=i: self.select_state(i))
            b.pack(side="left", padx=3)
            b.configure(fg=col if not sel else "white")
        self.show_state()

    def select_state(self, i):
        self._persist_form(silent=True)
        self.sel_state = max(0, min(i, len(self.states) - 1))
        self.refresh_states_ui()
        self._history_commit()

    def show_state(self):
        if not self.states:
            return
        # Snapshot EVERYTHING first: s is a live ref into self.states and each
        # .set() below fires a trace that persists the form back into it —
        # reading after writing would pick up stale-form corruption.
        s = self.states[self.sel_state]
        ap = dict(s.get("appearance", {})); mv = dict(s.get("movement", {}))
        label = s.get("label", ""); role = s.get("role", "")
        dur = str(s.get("duration", 0.5))
        shape = s.get("shape", "sphere"); ease = s.get("easing", "linear")
        size = str(ap.get("size", 8)); sizemax = str(ap.get("sizeMax", 12))
        color = ap.get("color", "#ffffff"); op = str(ap.get("opacity", 255))
        mins = str(mv.get("minSpeed", 0)); maxs = str(mv.get("maxSpeed", 0))
        cm = s.get("customModel") or {}
        cfile = cm.get("file", ""); cnode = cm.get("node", "")
        cnodes = list(cm.get("nodes") or [])
        if not cnodes and (s.get("modelRefs") or []):
            cnodes = [cnode] if cnode else []
        self._loading = True
        try:
            self.s_label.set(label); self.s_role.set(role)
            self.s_dur.set(dur)
            self.s_shape.set(shape); self.s_ease.set(ease)
            self.s_size.set(size); self.s_sizemax.set(sizemax)
            self.s_color.set(color); self.s_op.set(op)
            self.s_mins.set(mins); self.s_maxs.set(maxs)
            self.s_custom_file.set(cfile)
            self._rebuild_node_menu(cnodes, keep=cnode)
            self.lbl_custom_file.configure(text=cfile or "مفيش ملف",
                                           fg=TEXT if cfile else MUTED)
            try:
                self.color_swatch.configure(bg=self.s_color.get())
            except Exception:
                pass
        finally:
            self._loading = False
        self._update_custom_row()

    def add_state(self, role):
        self._persist_form(silent=True)
        self.states.append(default_state(role, len(self.states)))
        self.sel_state = len(self.states) - 1
        self.refresh_states_ui()
        self._history_commit()

    def del_state(self):
        if len(self.states) <= 2:
            messagebox.showwarning("تنبيه", "لازم birth + death")
            return
        self.states.pop(self.sel_state)
        self.sel_state = 0
        self.refresh_states_ui()
        self._history_commit()

    @staticmethod
    def _ease_fn(t, name):
        t = max(0.0, min(1.0, t))
        if name == "ease-in":
            return t * t
        if name == "ease-out":
            return t * (2 - t)
        if name == "ease-in-out":
            return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t
        return t

    def _build_tracks(self):
        """Per-particle keyframe tracks (birth→…→death), like the extension.
        Each entry: {dur, shape, size, sizeMax, color, opacity, minSpd, maxSpd, easing}."""
        tracks = []
        prev_shape = None
        for s in self.states:
            ap = s.get("appearance", {}); mv = s.get("movement", {})
            shp = str(s.get("shape", "") or "").lower() or prev_shape
            if self.ptype == "3d":
                shp = shp if shp in SHAPES_3D else "sphere"
            else:
                shp = shp if shp in SHAPES_2D else "circle"
            prev_shape = shp or ("sphere" if self.ptype == "3d" else "circle")
            tracks.append({
                "dur": max(1e-6, float(s.get("duration", 0.5) or 0.5)),
                "shape": prev_shape,
                "size": float(ap.get("size", 8) or 0),
                "sizeMax": float(ap.get("sizeMax", ap.get("size", 8)) or 0),
                "color": ap.get("color", "#ffffff") or "#ffffff",
                "opacity": float(ap.get("opacity", 255) if ap.get("opacity") is not None else 255),
                "minSpd": float(mv.get("minSpeed", 0) or 0),
                "maxSpd": float(mv.get("maxSpeed", mv.get("minSpeed", 0)) or 0),
                "easing": s.get("easing", "linear") or "linear",
            })
        return tracks

    @staticmethod
    def _locate(tracks, age):
        """Returns (k, eased_t, raw_t) for the interval containing age.
        Matches the extension exactly: intervals = states-1 with the FROM
        state's duration; the death state's own duration doesn't extend life.
        raw_t is the un-eased 0..1 progress (shape switches at raw>=0.5),
        eased_t applies the FROM state's easing (values morph)."""
        segs = max(1, len(tracks) - 1)
        total = sum(tracks[k]["dur"] for k in range(segs))
        t = max(0.0, min(age, total)) if total > 0 else 0.0
        acc = 0.0
        for k in range(segs):
            d = tracks[k]["dur"]
            if t < acc + d or k == segs - 1:
                raw = 0.0 if d <= 0 else max(0.0, min(1.0, (t - acc) / d))
                return k, StudioApp._ease_fn(raw, tracks[k]["easing"]), raw
            acc += d
        return segs - 1, 1.0, 1.0

    def _sample_tracks(self, tracks, age, sizeRatio, speedRatio):
        """Interpolate size/color/opacity/speed with easing; shape switches
        discretely exactly mid-segment (raw>=0.5) so birth->death with only
        2 states shows birth shape first half, death shape second half."""
        k, e, raw = self._locate(tracks, age)
        a, b = tracks[k], tracks[min(k + 1, len(tracks) - 1)]
        smin = a["size"] + (b["size"] - a["size"]) * e
        smax = a["sizeMax"] + (b["sizeMax"] - a["sizeMax"]) * e
        mn = a["minSpd"] + (b["minSpd"] - a["minSpd"]) * e
        mx = a["maxSpd"] + (b["maxSpd"] - a["maxSpd"]) * e
        shape = b["shape"] if raw >= 0.5 else a["shape"]
        return {
            "size": smin + (smax - smin) * sizeRatio,
            "color": self._lerp_color(a["color"], b["color"], e),
            "opacity": a["opacity"] + (b["opacity"] - a["opacity"]) * e,
            "speed": mn + (mx - mn) * speedRatio,
            "shape": shape,
        }

    def _is_custom_shape(self):
        try:
            return (self.s_shape.get() or "").lower() == "custom"
        except Exception:
            return False

    def _update_custom_row(self):
        """Show the model upload row only when Shape == custom (either mode);
        the Node picker only for 3D multi-node models. No var writes here."""
        try:
            show = self._is_custom_shape()
            if show:
                self.row_custom.pack(fill="x", pady=4)
                self.btn_upload.configure(
                    text="📦 Upload 3D" if self.ptype == "3d" else "🖼 Upload image")
                self.lbl_custom_hint.configure(
                    text="في GDevelop: ضيف الـ GLB كـ Resource وحطه في ModelsGLB"
                    if self.ptype == "3d" else
                    "في GDevelop: ضيف الصورة كـ Image resource")
                self.lbl_custom_hint.pack(fill="x", pady=(0, 2))
                if self.ptype == "3d" and len(getattr(self, "_custom_nodes", [])) > 1:
                    self.row_custom_node.pack(fill="x", pady=2)
                else:
                    self.row_custom_node.pack_forget()
            else:
                self.row_custom.pack_forget()
                self.row_custom_node.pack_forget()
                self.lbl_custom_hint.pack_forget()
        except Exception:
            pass

    def _rebuild_node_menu(self, nodes, keep=""):
        self._custom_nodes = list(nodes)
        menu = self.om_node["menu"]
        menu.delete(0, "end")
        if not nodes:
            menu.add_command(label="(الملف كله)", command=lambda: self.s_node.set(""))
            self.s_node.set("")
            return
        for n in nodes:
            menu.add_command(label=n, command=lambda v=n: self.s_node.set(v))
        self.s_node.set(keep if keep in nodes else nodes[0])

    def upload_custom_model(self):
        if self.ptype == "3d":
            p = filedialog.askopenfilename(
                filetypes=[("3D models", "*.glb *.gltf *.obj"), ("All", "*.*")])
            kind = "model"
        else:
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.svg"),
                           ("All", "*.*")])
            kind = "image"
        if not p:
            return
        fname = os.path.basename(p)
        nodes = model_nodes_from_file(p) if kind == "model" else []
        stem = os.path.splitext(fname)[0]
        self._loading = True
        try:
            self.s_custom_file.set(fname)
            self.lbl_custom_file.configure(text=fname, fg=TEXT)
            self._rebuild_node_menu(nodes, keep=self.s_node.get())
        finally:
            self._loading = False
        # persist file+node into the selected state (undo-safe)
        if self._persist_form(silent=True):
            self._sim_reset()
            self._history_commit()
        self._update_custom_row()

    def clear_custom_model(self):
        self._loading = True
        try:
            self.s_custom_file.set("")
            self.s_node.set("")
            self._rebuild_node_menu([])
            self.lbl_custom_file.configure(text="مفيش ملف", fg=MUTED)
        finally:
            self._loading = False
        if self._persist_form(silent=True):
            self._history_commit()
        self._update_custom_row()

    def pick_color(self):
        c = colorchooser.askcolor(self.s_color.get())
        if c and c[1]:
            self.s_color.set(c[1])
            try:
                self.color_swatch.configure(bg=c[1])
            except Exception:
                pass

    def _persist_form(self, silent=False):
        """Write the form fields back into the selected state. Returns True on success."""
        if not self.states or not (0 <= self.sel_state < len(self.states)):
            return False
        try:
            s = self.states[self.sel_state]
            s["label"] = self.s_label.get().strip() or s["role"]
            s["duration"] = float(self.s_dur.get())
            s["shape"] = self.s_shape.get(); s["easing"] = self.s_ease.get()
            s["appearance"] = {"size": float(self.s_size.get()),
                               "sizeMax": float(self.s_sizemax.get()),
                               "color": self.s_color.get(),
                               "opacity": int(float(self.s_op.get()))}
            s["movement"] = {"minSpeed": float(self.s_mins.get()),
                             "maxSpeed": float(self.s_maxs.get()),
                             "minRot": -90, "maxRot": 90}
            # custom shape model refs (upload row); untouched unless custom
            if (self.s_shape.get() or "").lower() == "custom":
                fname = (self.s_custom_file.get() or "").strip()
                node = (self.s_node.get() or "").strip()
                kind = "model" if self.ptype == "3d" else "image"
                s["customModel"] = {"file": fname, "node": node, "kind": kind,
                                    "nodes": list(getattr(self, "_custom_nodes", []))}
                if fname:
                    ref = node or os.path.splitext(fname)[0]
                    if kind == "model":
                        s["modelRefs"] = [ref]
                    else:
                        s["customShapeRefs"] = [fname]
            return True
        except (ValueError, IndexError, AttributeError):
            if not silent:
                messagebox.showerror("خطأ", "قيمة غلط في حقول الحالة")
            return False

    def save_state(self):
        if not self.states:
            return
        if self._persist_form():
            self.refresh_states_ui()
            self._sim_reset()
            self._history_commit()

    def apply_template(self, name):
        tpl = TEMPLATES[name]
        patch = tpl[self.ptype]  # version matching the ACTIVE editor (no type switch)
        em = default_emitter(self.ptype)
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(em.get(k), dict):
                em[k].update(v)
            else:
                em[k] = v
        self._load_emitter_to_ui(em)
        states_key = "states2d" if self.ptype == "2d" else "states3d"
        if tpl.get(states_key):
            self.states = copy.deepcopy(tpl[states_key])
            self.sel_state = 0
            self.refresh_states_ui()
        self._sim_reset()
        self._history_commit()

    # ---- file actions ----
    def do_new(self):
        self.filepath = None
        self.e_filename.delete(0, "end"); self.e_filename.insert(0, "Default")
        self._load_emitter_to_ui(default_emitter(self.ptype))
        self.states = [default_state("birth", 0), default_state("death", 1)]
        self.sel_state = 0
        self.refresh_states_ui(); self._sim_reset()
        self._history_commit()

    def do_open(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                eff = json.load(f)
            try:
                eff, _warns = migrate_effect(eff)
            except ValueError as ve:
                messagebox.showerror("خطأ", str(ve))
                return
            if _warns:
                debug_log("MIGRATE", p, " | ".join(_warns))
            self.filepath = p
            self.e_filename.delete(0, "end")
            self.e_filename.insert(0, os.path.splitext(os.path.basename(p))[0])
            self.ptype = eff.get("type", "2d")
            if self.ptype not in ("2d", "3d"):
                self.ptype = "2d"
            self.set_type(self.ptype, commit=False)
            self.states = eff.get("states", self.states)
            self.sel_state = 0
            self._load_emitter_to_ui(eff.get("emitter", default_emitter("2d")))
            self.refresh_states_ui(); self._sim_reset()
            self._history_commit()
        except Exception as e:
            messagebox.showerror("خطأ", str(e))

    def _gather(self):
        self.filename = self.e_filename.get().strip() or "Default"
        eff = self.current_effect()
        if eff is None:
            return None
        errs = validate_effect(eff)
        self.status.configure(text="✔ سليم — جاهز" if not errs else ("⚠ " + " | ".join(errs)),
                              fg=OK if not errs else WARN)
        return eff

    def do_save(self):
        if not self.filepath:
            return self.do_save_as()
        eff = self._gather()
        if eff is None:
            return
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(eff, f, indent=2, ensure_ascii=False)

    def do_save_as(self):
        eff = self._gather()
        if eff is None:
            return
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         initialfile=f"{self.filename}.json",
                                         filetypes=[("JSON", "*.json")])
        if p:
            self.filepath = p
            with open(p, "w", encoding="utf-8") as f:
                json.dump(eff, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("تم", f"اتصدّر:\n{p}\n\nضيفه في GDevelop كـ JSON resource وحطه في ParticleJSON.")

    # ================= viewport simulation =================
    def _sim_reset(self):
        self.parts = []
        self.accum = 0.0
        self.bursted = False
        self.last_t = time.time()
        self._cached_eff = None
        self._cache_t = 0.0
        self._eff_dirty = True
        self._last_sim_mode = None
        if getattr(self, "_cpp_eng", None) is not None:
            try:
                self._cpp_eng.reset()
            except Exception:
                pass
        self._cpp_key = None
        self._cpp_out = None

    def _spawn(self, em, cx, cy):
        cone = em.get("propagationCone", {})
        zone = em.get("emissionZone", {})
        is3d = "directionZ" in cone
        spread = cone.get("spread", 90)
        # morph tracks across ALL states (birth→…→death), jittered per particle.
        # Life = sum of all but the death duration (extension semantics).
        tracks = self._build_tracks()
        jitter = 0.9 + random.random() * 0.2
        for tr in tracks:
            tr["dur"] *= jitter
        life = max(0.1, sum(tr["dur"] for tr in tracks[:-1]))
        sizeRatio, speedRatio = random.random(), random.random()
        head = self._sample_tracks(tracks, 0.0, sizeRatio, speedRatio)
        spd0 = head["speed"]
        if is3d:
            # world-centered spawn (projected later); y up
            zshape = str(zone.get("shape", "sphere"))
            rot3 = math.radians(zone.get("rotationZ", zone.get("rotation", 0)) or 0)
            cr3, sr3 = math.cos(rot3), math.sin(rot3)
            if zshape == "sphere":
                th, ph = random.random() * math.pi * 2, math.acos(2 * random.random() - 1)
                rr = (zone.get("radius", 10) or 10) * (random.random() ** (1 / 3))
                sx, sy, sz = rr * math.sin(ph) * math.cos(th), rr * math.cos(ph), rr * math.sin(ph) * math.sin(th)
            elif zshape == "box":
                sx = (random.random() - 0.5) * (zone.get("width", 100) or 100)
                sy = (random.random() - 0.5) * (zone.get("height", 60) or 60)
                sz = (random.random() - 0.5) * (zone.get("depth", 60) or 60)
                sx, sy = sx * cr3 - sy * sr3, sx * sr3 + sy * cr3
            elif zshape == "line":
                sx = (random.random() - 0.5) * (zone.get("length", 100) or 100)
                sy, sz = 0.0, 0.0
                sx, sy = sx * cr3 - sy * sr3, sx * sr3 + sy * cr3
            else:
                sx, sy, sz = 0.0, 0.0, 0.0
            az, el = math.radians(cone.get("directionZ", 0)), math.radians(cone.get("directionY", 0))
            base = (math.cos(el) * math.cos(az), math.sin(el), math.cos(el) * math.sin(az))
            dx, dy, dz = self._cone_dir3(base[0], base[1], base[2], spread)
            # layout: [x,y,vx,vy,age,c0,c1,s0,s1,life,z,vz,shape,tracks,dx,dy,dz,gx,gy,gz,sizeRatio,speedRatio]
            ex, ey, ez = getattr(self, "emitter_pos", (0.0, 0.0, 0.0))
            if em.get("reverse"):
                dist = spd0 * life
                return [ex + sx + dx * dist, ey + sy + dy * dist,
                        -dx * spd0, -dy * spd0, 0.0, "", "", 0, 0, life,
                        ez + sz + dz * dist, -dz * spd0, head["shape"],
                        tracks, -dx, -dy, -dz, 0.0, 0.0, 0.0, sizeRatio, speedRatio]
            return [ex + sx, ey + sy, dx * spd0, dy * spd0, 0.0, "", "", 0, 0, life,
                    ez + sz, dz * spd0, head["shape"],
                    tracks, dx, dy, dz, 0.0, 0.0, 0.0, sizeRatio, speedRatio]
        ang = math.radians((cone.get("direction", 0)) + random.uniform(-spread / 2, spread / 2))
        # 2D zone sampling with rotation (mirrors the extension's spawnPos)
        zshape = str(zone.get("shape", "Circle")).lower()
        rot = math.radians(zone.get("rotation", 0) or 0)
        zmode = str(zone.get("mode", "Surface")).lower()
        lx, ly = 0.0, 0.0
        if zshape == "circle":
            rr = zone.get("radius", 50) or 50
            a = random.random() * math.pi * 2
            if zmode == "edge":
                lx, ly = math.cos(a) * rr, math.sin(a) * rr
            else:
                r = math.sqrt(random.random()) * rr
                lx, ly = math.cos(a) * r, math.sin(a) * r
        elif zshape == "rectangle":
            w, h = (zone.get("width", 100) or 100), (zone.get("height", 60) or 60)
            if zmode == "edge":
                per = 2 * (w + h)
                d = random.random() * per
                if d < w:
                    lx, ly = d - w / 2, -h / 2
                elif d < w + h:
                    lx, ly = w / 2, (d - w) - h / 2
                elif d < 2 * w + h:
                    lx, ly = w / 2 - (d - w - h), h / 2
                else:
                    lx, ly = -w / 2, h / 2 - (d - 2 * w - h)
            else:
                lx, ly = (random.random() - 0.5) * w, (random.random() - 0.5) * h
        elif zshape == "line":
            lx = (random.random() - 0.5) * (zone.get("length", 100) or 100)
        # point → (0,0); rotate local offset then translate to emitter
        ox, oy = lx * math.cos(rot) - ly * math.sin(rot), lx * math.sin(rot) + ly * math.cos(rot)
        dx, dy = math.cos(ang), math.sin(ang)
        if em.get("reverse"):
            dist = spd0 * life
            return [cx + ox + dx * dist, cy + oy + dy * dist,
                    -dx * spd0, -dy * spd0, 0.0, "", "", 0, 0, life, 0.0, 0.0, head["shape"],
                    tracks, -dx, -dy, 0.0, 0.0, 0.0, 0.0, sizeRatio, speedRatio]
        return [cx + ox, cy + oy,
                dx * spd0, dy * spd0, 0.0, "", "", 0, 0, life, 0.0, 0.0, head["shape"],
                tracks, dx, dy, 0.0, 0.0, 0.0, 0.0, sizeRatio, speedRatio]

    @staticmethod
    def _lerp_color(c0, c1, t, _cache={}):
        """Lerp two #rrggbb colors (cached parse). tkinter has no alpha."""
        def parse(c):
            if c not in _cache:
                h = (c or "#ffffff").lstrip("#")
                if len(h) == 3:
                    h = h[0] * 2 + h[1] * 2 + h[2] * 2
                try:
                    _cache[c] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                except ValueError:
                    _cache[c] = (255, 255, 255)
            return _cache[c]
        a, b = parse(c0), parse(c1)
        return "#%02x%02x%02x" % (round(a[0] + (b[0] - a[0]) * t),
                                  round(a[1] + (b[1] - a[1]) * t),
                                  round(a[2] + (b[2] - a[2]) * t))

    # ---- embedded (lightweight) preview: effect cached, ~25fps, ≤250 dots ----
    # For full 60FPS with thousands of particles use open_fast_preview().
    TK_MAX_DOTS = 250
    # C++ core path allows a higher in-app dot budget (tkinter Canvas stays
    # the real bottleneck; tuned by core/perf_test.py, default 800).
    CPP_MAX_DOTS = 800

    def _mark_dirty(self):
        self._eff_dirty = True

    def _cached_effect(self):
        now = time.time()
        if self._cached_eff is None or self._eff_dirty or now - self._cache_t > 0.15:
            self._cached_eff = self.current_effect(silent=True)
            self._cache_t = now
            self._eff_dirty = False
        return self._cached_eff

    def _tick(self):
        t0 = time.time()
        try:
            self._tick_body(t0)
        except Exception:
            # never let the viewport loop die silently; record and continue
            try:
                debug_log("TICK-EXC", traceback.format_exc().replace("\n", " | ")[:2000])
            except Exception:
                pass
        self.after(40, self._tick)

    def _tick_body(self, t0):
        dt = min(0.05, max(1e-3, t0 - self.last_t))
        self.last_t = t0
        eff = self._cached_effect()
        c = self.canvas
        W = max(100, c.winfo_width()); H = max(100, c.winfo_height())
        cx, cy = W * 0.5, H * 0.52
        if eff is not None and self.ptype == "2d":
            # spawn at emitter center (camera pan + gizmo offset); old dots stay world-locked
            scx = cx + self.cam["ox"] + self.emitter2d[0]
            scy = cy + self.cam["oy"] + self.emitter2d[1]
        else:
            scx, scy = cx, cy
        if eff is not None:
            em = eff["emitter"]
            g = em.get("gravity", {})
            gx = g.get("y", 0) * dt * 0.4
            gy = g.get("x", 0) * dt * 0.4
            gz = g.get("z", 0) * dt * 0.4
            mode = em.get("mode", "Infinite")
            if HAS_CPP_CORE:
                maxp = min(self.CPP_MAX_DOTS, int(em.get("maxParticles", 300) or 300))
            else:
                maxp = min(self.TK_MAX_DOTS, int(em.get("maxParticles", 300) or 300))
            if mode != self._last_sim_mode:
                # real-time: switching Infinite/Burst/One Shot restarts emission instantly
                self._last_sim_mode = mode
                self.parts = []
                self.accum = 0.0
                self.bursted = False
                if self._cpp_eng is not None:
                    try:
                        self._cpp_eng.reset()
                    except Exception:
                        self._cpp_eng = None
            cpp_n = 0
            cpp_active = False
            if HAS_CPP_CORE:
                try:
                    cpp_n = self._cpp_step(eff, em, dt, scx, scy, cx, cy,
                                           gx, gy, gz, maxp, W, H)
                    cpp_active = True
                except Exception:
                    # drop back to pure-Python sim (single frame cost only)
                    self._cpp_eng = None
                    self._cpp_key = None
                    self._cpp_out = None
            if not cpp_active:
                self._cpp_out = None
                if mode == "Burst":
                    if not self.bursted:
                        for _ in range(min(maxp, 150)):
                            self.parts.append(self._spawn(em, scx, scy))
                        self.bursted = True
                else:
                    flow = float(em.get("flow", 40) or 40)
                    self.accum += flow * dt
                    while self.accum >= 1 and len(self.parts) < maxp:
                        self.accum -= 1
                        self.parts.append(self._spawn(em, scx, scy))
                for p in self.parts:
                    # gravity accumulates independently (studio model)
                    p[17] += gx; p[18] += gy; p[19] += gz
                    # base velocity = dir * interpolated track speed (morphs over life)
                    smp = self._sample_tracks(p[13], p[4], p[20], p[21])
                    p[2] = p[14] * smp["speed"] + p[17]
                    p[3] = p[15] * smp["speed"] + p[18]
                    p[11] = p[16] * smp["speed"] + p[19]
                    p[0] += p[2] * dt; p[1] += p[3] * dt; p[10] += p[11] * dt; p[4] += dt
                if len(self.parts) > maxp or (self.parts and self.parts[0][4] >= self.parts[0][9]):
                    self.parts = [p for p in self.parts if p[4] < p[9]][-maxp:]
        else:
            self._cpp_out = None
            cpp_active = False
            cpp_n = 0
        self._draw(W, H, cx, cy, eff)
        fps = int(1 / max(time.time() - t0, 1e-3))
        n_show = cpp_n if cpp_active else len(self.parts)
        self.l_particles.configure(text=f"Particles: {n_show}")
        self.l_fps.configure(text=f"FPS: {min(fps, 120)} · {'C++' if cpp_active else 'PY'}")
        # periodic GL telemetry (diagnoses blank-GPU reports from the field)
        try:
            dbg_n = getattr(self, "_dbg_n", 0) + 1
            self._dbg_n = dbg_n
            if dbg_n % 150 == 1:
                ph = getattr(self, "_gl_photo", None)
                debug_log("tickstat", f"n={n_show}",
                          f"glphoto={ph.width()}x{ph.height()}" if ph else "glphoto=None",
                          f"glalive={getattr(getattr(self, '_gl', None), 'ok', '-')}")
        except Exception:
            pass

    def _cpp_step(self, eff, em, dt, scx, scy, cx, cy, gx, gy, gz, maxp, W, H):
        """Advance the C++ sim core and fetch draw-ready arrays.
        Returns the active particle count. Raises on core errors (caller falls
        back to the pure-Python sim)."""
        del em  # emitter travels inside configure(); kept for signature clarity
        if self._cpp_eng is None:
            self._cpp_eng = _CPP_MOD.Engine()
            self._cpp_eng.set_seed(random.randrange(1 << 30))
            self._cpp_key = None
        key = (self.ptype, self._cache_t)
        if key != self._cpp_key:
            self._cpp_eng.configure(eff["emitter"], self._build_tracks(),
                                    self.ptype == "3d")
            self._cpp_key = key
        if self.ptype == "3d":
            # same focal model as _draw3d (FOV control)
            self.cam["focal"] = ((max(100, H) * 0.5) /
                                 max(0.05, math.tan(math.radians(self._get_fov() / 2))))
        ex, ey, ez = getattr(self, "emitter_pos", (0.0, 0.0, 0.0))
        out = self._cpp_eng.step(dt, scx, scy, ex, ey, ez, gx, gy, gz, maxp,
                                 self.cam["yaw"], self.cam["pitch"], self.cam["zoom"],
                                 self.cam["ox"], self.cam["oy"],
                                 self.cam.get("focal", 620.0), cx, cy)
        self._cpp_out = out
        return len(out["x"])

    def _draw(self, W, H, cx, cy, eff):
        c = self.canvas
        c.delete("all")
        is3d = self.ptype == "3d" and eff is not None and "directionZ" in eff.get("emitter", {}).get("propagationCone", {})
        if is3d:
            self._draw3d(c, W, H, cx, cy, eff["emitter"])
            return
        cpp_out = getattr(self, "_cpp_out", None)
        c.create_rectangle(0, 0, W, H, fill="#16171f", outline="")
        # camera pan (middle-drag) moves the grid; gizmo drag moves the emitter only
        gx, gy = cx + self.cam["ox"], cy + self.cam["oy"]
        ex, ey = gx + self.emitter2d[0], gy + self.emitter2d[1]
        # perspective floor grid, always under the GPU layer (aligned 1:1)
        horizon = H * 0.42 + self.cam["oy"]
        c.create_line(0, horizon, W, horizon, fill="#3a3d55")
        for i in range(1, 9):
            y = horizon + (H - horizon) * (i / 9) ** 1.6
            c.create_line(0, y, W, y, fill="#2c2e44")
        step = max(1, W / 14)
        i = -10
        while i <= 10:
            c.create_line(gx, horizon, gx + i * step, H, fill="#2c2e44")
            i += 1
        gl_pos = self._gl_frame_2d(W, H, cx, cy, cpp_out) if cpp_out else None
        gl_done = gl_pos is not None
        if gl_done:
            c.create_image(gl_pos[0], gl_pos[1], anchor="nw", image=self._gl_photo)
        if eff is None:
            return
        em = eff["emitter"]
        # emission zone guide (rotated for rectangle/line so Rotation is visible)
        if bool(em.get("emissionZone", {}).get("showZone", True)):
            z = em.get("emissionZone", {})
            zs = str(z.get("shape", "Circle")).lower()
            try:
                rot = math.radians(float(z.get("rotation", 0) or 0))
            except (ValueError, TypeError):
                rot = 0.0
            cr, sr = math.cos(rot), math.sin(rot)
            def _rot2(x, y):
                return (ex + x * cr - y * sr, ey + x * sr + y * cr)
            if zs == "rectangle":
                try:
                    w, h = (z.get("width", 100) or 100) / 2, (z.get("height", 60) or 60) / 2
                except (ValueError, TypeError):
                    w, h = 50, 30
                q = [_rot2(-w, -h), _rot2(w, -h), _rot2(w, h), _rot2(-w, h)]
                c.create_polygon(q[0][0], q[0][1], q[1][0], q[1][1], q[2][0], q[2][1],
                                 q[3][0], q[3][1], outline="#4d9fff", fill="", dash=(4, 3))
            elif zs == "line":
                try:
                    ln = (z.get("length", 100) or 100) / 2
                except (ValueError, TypeError):
                    ln = 50
                a, b = _rot2(-ln, 0), _rot2(ln, 0)
                c.create_line(a[0], a[1], b[0], b[1], fill="#4d9fff", dash=(4, 3))
            elif zs != "point":
                try:
                    r = max(4.0, float(self.v_radius.get()))
                except ValueError:
                    r = 10.0
                c.create_oval(ex - r, ey - r, ex + r, ey + r, outline="#4d9fff", dash=(4, 3))
        # cone wireframe
        cone = em.get("propagationCone", {})
        if bool(cone.get("showCone", True)):
            try:
                base = float(cone.get("directionZ", cone.get("direction", 0)))
                spread = float(cone.get("spread", 90))
            except ValueError:
                base, spread = 0, 90
            if spread < 360:
                L = 110
                a1 = math.radians(base - spread / 2); a2 = math.radians(base + spread / 2)
                x1, y1 = ex + math.cos(a1) * L, ey + math.sin(a1) * L
                x2, y2 = ex + math.cos(a2) * L, ey + math.sin(a2) * L
                c.create_line(ex, ey, x1, y1, fill=YELLOW)
                c.create_line(ex, ey, x2, y2, fill=YELLOW)
                c.create_arc(ex - L, ey - L, ex + L, ey + L,
                             start=-(base + spread / 2), extent=spread,
                             outline=YELLOW, style="arc")
        # particles — GPU image, else halo pass (fake glow) then cores
        if gl_done:
            pass  # GL layer already placed first (below); guides/gizmo follow
        elif cpp_out is not None:
            # C++ fast path: draw-ready arrays, no per-particle Python sampling
            xs, ys, rs = cpp_out["x"], cpp_out["y"], cpp_out["r"]
            cs, ss = cpp_out["color"], cpp_out["shape"]
            n = len(xs)
            if self._glow_on(n):
                for i in range(n):
                    col = "#%06x" % cs[i]
                    hr = rs[i] * 2.2
                    c.create_oval(xs[i] - hr, ys[i] - hr, xs[i] + hr, ys[i] + hr,
                                  fill=self._halo_of(col), outline="")
            for i in range(n):
                self._draw_shape_2d(c, xs[i], ys[i], rs[i],
                                    SHAPE_ORDER[ss[i]], "#%06x" % cs[i])
        else:
            dots = []
            for p in self.parts:
                fill, r, shape = self._dot_color_size(p)
                dots.append((p[0], p[1], r, shape, fill))
            if self._glow_on(len(dots)):
                for x, y, r, shape, fill in dots:
                    hr = r * 2.2
                    c.create_oval(x - hr, y - hr, x + hr, y + hr,
                                  fill=self._halo_of(fill), outline="")
            for x, y, r, shape, fill in dots:
                self._draw_shape_2d(c, x, y, r, shape, fill)
        self._vignette(c, W, H)  # edge strips over scene, under gizmo
        # 2D gizmo: X red right, Y blue up + grab dot (left-drag moves emitter)
        c.create_line(ex, ey, ex + 95, ey, fill="#ff3b3b", width=3, arrow="last",
                      arrowshape=(12, 14, 6))
        c.create_line(ex, ey, ex, ey - 95, fill="#2f6bff", width=3, arrow="last",
                      arrowshape=(12, 14, 6))
        c.create_oval(ex - 8, ey - 8, ex + 8, ey + 8, fill="white", outline="#7b61ff", width=2)

    def _flip_glow(self):
        try:
            self.v_glow.set(not self.v_glow.get())
            self.b_glow.configure(text="✨ Glow: On" if self.v_glow.get() else "✨ Glow: Off")
        except Exception:
            pass

    def _flip_gpu(self):
        try:
            self.v_gpu.set(not self.v_gpu.get())
            self.b_gpu.configure(text="🎮 GPU: On" if self.v_gpu.get() else "🎮 GPU: Off")
        except Exception:
            pass

    def _gl_view(self):
        """Lazy offscreen GPU renderer (None => canvas-item fallback)."""
        if not HAS_GL_VIEW:
            return None
        try:
            if not self.v_gpu.get():
                return None
        except Exception:
            pass
        gl = getattr(self, "_gl", None)
        if gl is not None:
            return gl if getattr(gl, "ok", False) else None
        import time as _t
        if _t.time() < getattr(self, "_gl_retry_t", 0):
            return None  # cool down between failed inits
        try:
            # frozen exe: point glfw at the bundled DLL explicitly
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass and "PYGLFW_LIBRARY" not in os.environ:
                cand = os.path.join(meipass, "glfw", "glfw3.dll")
                if os.path.isfile(cand):
                    os.environ["PYGLFW_LIBRARY"] = cand
            gl = GLView()
            if getattr(gl, "ok", False):
                self._gl = gl
                debug_log("gl-init-ok")
                return gl
            debug_log("gl-init-failed")
        except Exception:
            debug_log("gl-init-exc", traceback.format_exc().replace("\n", " | ")[:500])
        self._gl = None
        self._gl_retry_t = _t.time() + 2.0
        return None

    @staticmethod
    def _gl_split(out):
        """cpp_out arrays -> (buckets, glow_all) of (x,y,z,s,r,g,b,a) tuples."""
        xs, ys, zs = out["x"], out["y"], out["z"]
        rs, cs, ss = out["r"], out["color"], out["shape"]
        aa = out.get("alpha", None)
        n = len(xs)
        buckets = {}
        glow = []
        for i in range(n):
            c = cs[i]
            t = ((xs[i], ys[i], zs[i], rs[i],
                  ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0,
                  (c & 255) / 255.0, aa[i] if aa else 1.0))
            buckets.setdefault(SHAPE_ORDER[ss[i]], []).append(t)
            glow.append(t)
        return buckets, glow

    def _gl_grid_2d(self, W, H, gx, horizon):
        step = max(1, W / 14)
        rest, top = [], [0.0, horizon, 0.0, float(W), horizon, 0.0]
        for k in range(1, 9):
            y = horizon + (H - horizon) * (k / 9) ** 1.6
            top += [0.0, y, 0.0, float(W), y, 0.0]
        i = -10
        while i <= 10:
            rest += [gx, horizon, 0.0, gx + i * step, float(H), 0.0]
            i += 1
        c1 = (0x2c / 255, 0x2e / 255, 0x44 / 255)
        c2 = (0x3a / 255, 0x3d / 255, 0x55 / 255)
        return [(rest, c1), (top, c2)]

    @staticmethod
    def _gl_grid_3d():
        segs = []
        k = -5
        while k <= 5:
            d = k * 52.0
            segs += [-260.0, 0.0, d, 260.0, 0.0, d,
                     d, 0.0, -260.0, d, 0.0, 260.0]
            k += 1
        return [(segs, (0x2c / 255, 0x2e / 255, 0x44 / 255))]

    @staticmethod
    def _gl_bbox(out, W, H):
        """Dirty region around live particles (+glow margin). None if empty."""
        xs, ys, rs = out["x"], out["y"], out["r"]
        if not xs:
            return None
        m = 6.0
        for r in rs:
            mm = r * 2.6 + 6.0
            if mm > m:
                m = mm
        x0 = max(0, int(min(xs) - m)); y0 = max(0, int(min(ys) - m))
        x1 = min(W - 1, int(max(xs) + m)); y1 = min(H - 1, int(max(ys) + m))
        if x1 <= x0 or y1 <= y0:
            return None
        w2, h2 = x1 - x0 + 1, y1 - y0 + 1
        if w2 * h2 > 0.7 * W * H:
            return (0, 0, W, H)  # near-fullscreen: subrect not worth it
        return (x0, y0, w2, h2)

    def _gl_photo_update(self, ppm_bytes):
        """Push raw PPM bytes to the reused canvas photo. No canvas items."""
        try:
            if getattr(self, "_gl_photo", None) is None:
                self._gl_photo = tk.PhotoImage(data=ppm_bytes, format="ppm")
            else:
                self._gl_photo.configure(data=ppm_bytes, format="ppm")
            return True
        except Exception:
            debug_log("gl-show-exc", traceback.format_exc().replace("\n", " | ")[:300])
            self._gl_photo = None
            return False

    def _gl_show(self, ppm_bytes, x=0, y=0):
        if not self._gl_photo_update(ppm_bytes):
            return False
        try:
            self.canvas.create_image(x, y, anchor="nw", image=self._gl_photo)
            return True
        except Exception:
            return False

    def _gl_frame_2d(self, W, H, cx, cy, out):
        gl = self._gl_view()
        if gl is None or out is None or not len(out["x"]):
            return None
        try:
            from render.gl_view import mat_ortho as _ortho
            buckets, glow = self._gl_split(out)
            if not self._glow_on(len(out["x"])):
                glow = []
            gx = cx + self.cam["ox"]
            horizon = H * 0.42 + self.cam["oy"]
            box = self._gl_bbox(out, W, H)
            if box is None:
                return None
            x0, y0, w2, h2 = box
            ppm = gl.render(buckets, glow, W, H, ortho=1,
                            clip=_ortho(0, W, 0, H, -1000, 1000),
                            zoom=1.0, focal=620.0,
                            bg=(22 / 255, 23 / 255, 31 / 255),
                            grid=self._gl_grid_2d(W, H, gx, horizon),
                            vp=(x0, y0, w2, h2))
            return (x0, y0) if self._gl_photo_update(ppm) else None
        except Exception:
            debug_log("gl-frame2d-exc", traceback.format_exc().replace("\n", " | ")[:500])
            self._gl = None
            return None

    def _gl_frame_3d(self, W, H, cx, cy, out, em):
        gl = self._gl_view()
        if gl is None or out is None or not len(out["x"]):
            return None
        try:
            from render.gl_view import mat_clip_3d as _clip, orbit_right_up as _ru
            n = len(out["x"])
            buckets = {}
            glow = []
            xs, zs, rs = out["wx"], out["z"], out["r"]
            ys, cs, ss = out["wy"], out["color"], out["shape"]
            aa = out.get("alpha", None)
            dep = out["depth"]
            f = self.cam.get("focal", 620.0)
            zoom = self.cam["zoom"]
            for i in range(n):
                c = cs[i]
                # NOTE: iScale stays in SCREEN px here; the vertex shader
                # unprojects it exactly once (dividing here too = tiny dots).
                t = (xs[i], ys[i], zs[i], rs[i],
                     ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0,
                     (c & 255) / 255.0, aa[i] if aa else 1.0)
                buckets.setdefault(SHAPE_ORDER[ss[i]], []).append(t)
                glow.append(t)
            if not self._glow_on(n):
                glow = []
            ru, uu = _ru(self.cam["yaw"], self.cam["pitch"])
            clip = _clip(self.cam["yaw"], self.cam["pitch"], zoom, f,
                         W, H, cx, cy, self.cam["ox"], self.cam["oy"])
            box = self._gl_bbox(out, W, H)
            if box is None:
                return None
            ppm = gl.render(buckets, glow, W, H, ortho=0, clip=clip,
                            zoom=zoom, focal=f, right=ru, up=uu,
                            bg=(20 / 255, 21 / 255, 28 / 255),
                            grid=self._gl_grid_3d(), vp=box)
            return ((box[0], box[1])
                    if self._gl_photo_update(ppm) else None)
        except Exception:
            debug_log("gl-frame3d-exc", traceback.format_exc().replace("\n", " | ")[:500])
            self._gl = None
            return None

    def _glow_on(self, n):
        """Halos only when enabled and few enough dots (protects fps)."""
        try:
            return bool(self.v_glow.get()) and n <= 450
        except Exception:
            return False

    @staticmethod
    def _hex_rgb(col):
        h = (col or "#ffffff").lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return (255, 255, 255)

    @classmethod
    def _halo_of(cls, col):
        """Dimmed halo color (fakes additive glow on alpha-less canvas)."""
        r, g, b = cls._hex_rgb(col)
        return "#%02x%02x%02x" % (r * 35 // 100, g * 35 // 100, b * 35 // 100)

    @classmethod
    def _depth_shade(cls, col, depth, focal=620.0, bg=(20, 21, 28)):
        """Far particles melt into the bg (depth cue without alpha)."""
        try:
            dim = focal / (focal + float(depth))
        except (ValueError, TypeError, ZeroDivisionError):
            dim = 1.0
        dim = max(0.30, min(1.0, dim))
        r, g, b = cls._hex_rgb(col)
        t = 1.0 - dim
        return "#%02x%02x%02x" % (round(r + (bg[0] - r) * t),
                                  round(g + (bg[1] - g) * t),
                                  round(b + (bg[2] - b) * t))

    @staticmethod
    def _vignette(c, W, H):
        """Real vignette: 4 dark edge strips over the finished scene
        (particles + grid), always below the gizmo. Must run AFTER the
        particle layer, otherwise it buries the GPU image underneath."""
        m = min(W, H)
        t = max(14, m * 0.07)
        col = "#0e1016"
        c.create_rectangle(0, 0, W, t, fill=col, outline="")
        c.create_rectangle(0, H - t, W, H, fill=col, outline="")
        c.create_rectangle(0, 0, t, H, fill=col, outline="")
        c.create_rectangle(W - t, 0, W, H, fill=col, outline="")

    def _dot_color_size(self, p):
        """Shared color/size/shape policy for both 2D and 3D drawing.
        Gradient mode samples the full keyframe morph; selected mode uses the
        live form values. Returns (fill, radius, shape)."""
        if self.v_colormode.get() == "متدرج":
            smp = self._sample_tracks(p[13], p[4], p[20], p[21])
            return (smp["color"], max(1.5, smp["size"] * 0.45), smp["shape"])
        import re as _re
        col = (self.s_color.get() or "").strip()
        if not _re.fullmatch(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", col):
            st = self.states[self.sel_state] if 0 <= self.sel_state < len(self.states) else None
            col = ((st.get("appearance", {}) if st else {}).get("color") or "#ffffff")
        try:
            r0 = max(1.5, float(self.s_size.get()) * 0.45)
        except (ValueError, TypeError):
            r0 = 4.0
        shp = (self.s_shape.get() or "").lower()
        ok = SHAPES_3D if self.ptype == "3d" else SHAPES_2D
        return (col, r0, shp if shp in ok else ok[0])

    @staticmethod
    def _poly_2d(shape, x, y, r):
        """Pure geometry for 2D particle shapes (headless-testable).
        Returns (kind, payload): oval/rect→bbox, poly→flat pts, line→(x0,y0,x1,y1)."""
        if shape == "square":
            return ("rect", (x - r, y - r, x + r, y + r))
        if shape == "triangle":
            tr = r * 1.25
            pts = []
            for i in range(3):
                a = (i / 3) * math.pi * 2 - math.pi / 2
                pts += [x + math.cos(a) * tr, y + math.sin(a) * tr]
            return ("poly", pts)
        if shape == "diamond":
            return ("poly", [x, y - r, x + r, y, x, y + r, x - r, y])
        if shape == "star":
            pts = []
            for i in range(10):
                a = (i / 10) * math.pi * 2 - math.pi / 2
                rr = r if i % 2 == 0 else r * 0.45
                pts += [x + math.cos(a) * rr, y + math.sin(a) * rr]
            return ("poly", pts)
        if shape == "line":
            return ("line", (x - r * 1.6, y, x + r * 1.6, y))
        if shape == "custom":
            return ("hollow", (x - r, y - r, x + r, y + r))
        return ("oval", (x - r, y - r, x + r, y + r))

    def _draw_shape_2d(self, c, x, y, r, shape, fill):
        kind, pay = self._poly_2d(shape, x, y, r)
        if kind == "rect":
            c.create_rectangle(*pay, fill=fill, outline="")
        elif kind == "poly":
            c.create_polygon(pay, fill=fill, outline="")
        elif kind == "line":
            c.create_line(*pay, fill=fill, width=max(2, int(r * 0.5)))
        elif kind == "hollow":
            c.create_oval(*pay, outline=fill, width=2)
        else:
            c.create_oval(*pay, fill=fill, outline="")

    def _draw_shape_3d(self, c, sx, sy, r, shape, fill):
        """Projected 3D solids, ≤2 canvas items each (perf-safe)."""
        if shape == "cube":
            h = r * 0.9
            o = h * 0.45
            dark = self._lerp_color(fill, "#000000", 0.35)
            c.create_polygon(sx - h + o, sy - h - o, sx + h + o, sy - h - o,
                             sx + h, sy - h, sx - h, sy - h, fill=dark, outline="")
            c.create_rectangle(sx - h, sy - h, sx + h, sy + h, fill=fill, outline="")
        elif shape == "pyramid":
            dark = self._lerp_color(fill, "#000000", 0.35)
            c.create_polygon(sx - r, sy + r * 0.7, sx + r, sy + r * 0.7,
                             sx + r * 0.5, sy + r * 0.2, sx - r * 0.5, sy + r * 0.2,
                             fill=dark, outline="")
            c.create_polygon(sx, sy - r, sx + r, sy + r * 0.7, sx - r, sy + r * 0.7,
                             fill=fill, outline="")
        elif shape == "torus":
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=fill, outline="")
            c.create_oval(sx - r * 0.45, sy - r * 0.45, sx + r * 0.45, sy + r * 0.45,
                          fill="#14151c", outline="")
        elif shape == "diamond":
            c.create_polygon(sx, sy - r, sx + r * 0.7, sy, sx, sy + r, sx - r * 0.7, sy,
                             fill=fill, outline="")
        elif shape in ("square", "billboard"):
            c.create_rectangle(sx - r, sy - r, sx + r, sy + r, fill=fill, outline="")
        elif shape == "triangle":
            c.create_polygon(sx, sy - r, sx + r, sy + r * 0.8, sx - r, sy + r * 0.8,
                             fill=fill, outline="")
        elif shape == "star":
            _, pay = self._poly_2d("star", sx, sy, r)
            c.create_polygon(pay, fill=fill, outline="")
        elif shape == "line":
            c.create_line(sx - r * 1.6, sy, sx + r * 1.6, sy, fill=fill, width=max(2, int(r * 0.5)))
        elif shape == "custom":
            c.create_rectangle(sx - r, sy - r, sx + r, sy + r, outline=fill, width=2)
        else:  # sphere + fallback
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=fill, outline="")

    def _draw3d(self, c, W, H, cx, cy, em):
        """True 3D viewport: world (x right, y up, z toward viewer), orbit camera."""
        cpp_out = getattr(self, "_cpp_out", None)
        c.create_rectangle(0, 0, W, H, fill="#14151c", outline="")
        # focal from FOV: f = (H/2) / tan(fov/2)
        self.cam["focal"] = (max(100, H) * 0.5) / max(0.05, math.tan(math.radians(self._get_fov() / 2)))
        P = lambda x, y, z: self._proj(x, y, z, cx, cy)
        # floor grid on y=0 plane, always under the GPU layer (aligned 1:1)
        R, STEP = 260, 52
        for k in range(-R // STEP, R // STEP + 1):
            d = k * STEP
            x1, y1, _, _ = P(-R, 0, d); x2, y2, _, _ = P(R, 0, d)
            c.create_line(x1, y1, x2, y2, fill="#2c2e44")
            x1, y1, _, _ = P(d, 0, -R); x2, y2, _, _ = P(d, 0, R)
            c.create_line(x1, y1, x2, y2, fill="#2c2e44")
        gl_pos = self._gl_frame_3d(W, H, cx, cy, cpp_out, em) if cpp_out else None
        gl_done = gl_pos is not None
        if gl_done:
            c.create_image(gl_pos[0], gl_pos[1], anchor="nw", image=self._gl_photo)
        zone = em.get("emissionZone", {})
        EX, EY, EZ = self.emitter_pos
        if bool(zone.get("showZone", True)):
            zs = str(zone.get("shape", "sphere"))
            if zs == "sphere":
                try:
                    r = max(4.0, float(self.v_radius.get()))
                except ValueError:
                    r = 10.0
                sx, sy, sc, _ = P(EX, EY, EZ)
                c.create_oval(sx - r * sc, sy - r * sc, sx + r * sc, sy + r * sc,
                              outline="#4d9fff", dash=(4, 3))
            elif zs == "box":
                try:
                    w = float(self.v_width.get()) / 2; h = float(self.v_height.get()) / 2
                    d = float(self.v_depth.get()) / 2
                    rz = math.radians(float(self.v_rot.get()))
                except ValueError:
                    w, h, d, rz = 50, 30, 30, 0.0
                crz, srz = math.cos(rz), math.sin(rz)
                v = [(-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
                     (-w, -h, d), (w, -h, d), (w, h, d), (-w, h, d)]
                v = [(EX + x * crz - y * srz, EY + x * srz + y * crz, EZ + z) for (x, y, z) in v]
                q = [P(*p)[:2] for p in v]
                for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                             (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
                    c.create_line(q[a][0], q[a][1], q[b][0], q[b][1], fill="#4d9fff", dash=(4, 3))
            elif zs == "line":
                try:
                    ln = (zone.get("length", 100) or 100) / 2
                    rz = math.radians(float(zone.get("rotationZ", zone.get("rotation", 0)) or 0))
                except (ValueError, TypeError):
                    ln, rz = 50, 0.0
                crz, srz = math.cos(rz), math.sin(rz)
                a = P(EX - ln * crz, EY - ln * srz, EZ)[:2]; b = P(EX + ln * crz, EY + ln * srz, EZ)[:2]
                c.create_line(a[0], a[1], b[0], b[1], fill="#4d9fff", dash=(4, 3))
        # cone wireframe
        cone = em.get("propagationCone", {})
        if bool(cone.get("showCone", True)):
            try:
                spread = float(cone.get("spread", 90))
                az, el = math.radians(float(cone.get("directionZ", 0))), math.radians(float(cone.get("directionY", 0)))
            except ValueError:
                spread, az, el = 90, 0.0, 0.0
            if spread < 360:
                bx, by, bz = math.cos(el) * math.cos(az), math.sin(el), math.cos(el) * math.sin(az)
                L = 110.0
                # two edge rays via basis perpendiculars
                ux, uy, uz = (0.0, 1.0, 0.0) if abs(by) < 0.95 else (1.0, 0.0, 0.0)
                ex, ey, ez = by * uz - bz * uy, bz * ux - bx * uz, bx * uy - by * ux
                n = math.sqrt(ex * ex + ey * ey + ez * ez) or 1.0
                ex, ey, ez = ex / n, ey / n, ez / n
                off = math.tan(math.radians(spread / 2))
                for sgn in (1.0, -1.0):
                    dx, dy, dz = bx + ex * off * sgn, by + ey * off * sgn, bz + ez * off * sgn
                    n2 = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                    x1, y1, _, _ = P(EX, EY, EZ)
                    x2, y2, _, _ = P(EX + dx / n2 * L, EY + dy / n2 * L, EZ + dz / n2 * L)
                    c.create_line(x1, y1, x2, y2, fill=YELLOW)
        # particles, far → near (far melts into bg = depth cue)
        cpp_out = getattr(self, "_cpp_out", None)
        focal = self.cam.get("focal", 620.0)
        if gl_done:
            pass  # GL layer already placed first (below); guides/gizmo follow
        elif cpp_out is not None:
            # C++ fast path: screen coords + depth precomputed, painter order
            order = sorted(range(len(cpp_out["x"])), key=cpp_out["depth"].__getitem__)
            for i in order:
                col = self._depth_shade("#%06x" % cpp_out["color"][i],
                                        cpp_out["depth"][i], focal)
                self._draw_shape_3d(c, cpp_out["x"][i], cpp_out["y"][i],
                                    cpp_out["r"][i], SHAPE_ORDER[cpp_out["shape"][i]],
                                    col)
        else:
            projs = []
            for p in self.parts:
                sx, sy, sc, depth = P(p[0], p[1], p[10])
                projs.append((depth, sx, sy, sc, p))
            projs.sort(key=lambda t: t[0])
            for depth, sx, sy, sc, p in projs:
                fill, r, shape = self._dot_color_size(p)
                fill = self._depth_shade(fill, depth, focal)
                self._draw_shape_3d(c, sx, sy, max(1.0, r * sc), shape, fill)
        self._vignette(c, W, H)  # edge strips over scene, under gizmo
        # axes gizmo: X red, Y green, Z blue (draggable with left-click)
        ox, oy, _, _ = P(EX, EY, EZ)
        for (ax, ay, az, col) in [(70, 0, 0, "#ff3b3b"), (0, 70, 0, OK), (0, 0, 70, "#2f6bff")]:
            ex, ey, _, _ = P(EX + ax, EY + ay, EZ + az)
            c.create_line(ox, oy, ex, ey, fill=col, width=3, arrow="last", arrowshape=(10, 12, 5))
        c.create_oval(ox - 6, oy - 6, ox + 6, oy + 6, fill="white", outline="")

    # ================= fast 60FPS browser preview (TypeScript engine) =================
    _preview_server = None
    _preview_port = 0

    def open_fast_preview(self):
        """Export current effect to preview/last_effect.json and open the
        TypeScript 60FPS preview in the browser (live-sync every 500ms)."""
        eff = self._gather()
        if eff is None:
            return
        blobs = model_blobs_for_states(self.states)
        if blobs:
            eff["modelsData"] = blobs
        base = app_base_dir()
        pv_dir = os.path.join(base, "preview")
        try:
            os.makedirs(pv_dir, exist_ok=True)
            with open(os.path.join(pv_dir, "last_effect.json"), "w", encoding="utf-8") as f:
                json.dump(eff, f, ensure_ascii=False)
        except OSError as e:
            messagebox.showerror("خطأ", f"تعذر كتابة ملف المعاينة:\n{e}")
            return
        if StudioApp._preview_server is None:
            handler = partial(_QuietHTTPHandler, directory=base)
            try:
                srv = _PreviewHTTPServer(("127.0.0.1", 0), handler)
            except OSError as e:
                messagebox.showerror("خطأ", f"تعذر تشغيل سيرفر المعاينة: {e}")
                return
            StudioApp._preview_port = srv.server_address[1]
            StudioApp._preview_server = srv
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{StudioApp._preview_port}/preview/preview.html"
        # self-contained live page: bundle + effect inlined => zero network
        # fetches (proxy/firewall-proof). Falls back to classic live page.
        try:
            with open(os.path.join(pv_dir, "preview.html"), encoding="utf-8") as f:
                tpl = f.read()
            with open(os.path.join(pv_dir, "live_bundle.js"), encoding="utf-8") as f:
                bundle = f.read()
            boot = json.dumps(eff, ensure_ascii=False).replace("</", "<\\/")
            page = tpl.replace('<script type="module" src="./main.js"></script>',
                               "<script type=\"module\">\n" + bundle + "\n</script>", 1)
            page = page.replace('<script id="boot-effect" type="application/json"></script>',
                                '<script id="boot-effect" type="application/json">'
                                + boot + "</script>", 1)
            if page == tpl or "live_bundle" in page or "__previewBooted" not in page:
                raise ValueError("template markers missing")
            with open(os.path.join(pv_dir, "live_effect.html"), "w", encoding="utf-8") as f:
                f.write(page)
            url = f"http://127.0.0.1:{StudioApp._preview_port}/preview/live_effect.html"
        except Exception:
            pass
        # self-check: prove WE serve before opening the browser, otherwise the
        # user gets a dead tab (proxy/firewall/CWD issues stay visible here)
        try:
            import urllib.request as _url
            opener = _url.build_opener(_url.ProxyHandler({}))  # localhost, no proxy
            with opener.open(url, timeout=5) as _r:
                if getattr(_r, "status", 200) != 200:
                    raise OSError(f"HTTP {getattr(_r, 'status', '?')}")
        except Exception as e:
            messagebox.showerror("خطأ", f"سيرفر المعاينة مش بيرد:\n{e}")
            return
        # keep file fresh while window is open (live slider edits, single loop)
        if not getattr(self, "_live_push_on", False):
            self._live_push_on = True
            self._push_live_preview()
        webbrowser.open(url)

    def _push_live_preview(self):
        try:
            eff = self.current_effect(silent=True)
            if eff is not None:
                fp = model_fingerprint(self.states)
                if getattr(self, "_models_fp", None) != fp:
                    self._models_fp = fp
                    eff["modelsData"] = model_blobs_for_states(self.states)
                with open(os.path.join(app_base_dir(), "preview", "last_effect.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(eff, f, ensure_ascii=False)
        except Exception:
            pass
        self.after(500, self._push_live_preview)


if __name__ == "__main__":
    if "--probe-gl" in sys.argv:
        # headless GPU check (used to verify frozen exe too): no Tk needed
        try:
            from render.gl_view import GLView, mat_ortho
            _v = GLView()
            assert _v.ok, "GL init failed"
            _png = _v.render(
                {"circle": [(100.0, 100.0, 0.0, 10.0, 1.0, 0.5, 0.0, 1.0)]},
                [(100.0, 100.0, 0.0, 10.0, 1.0, 0.5, 0.0, 1.0)],
                320, 200, ortho=1,
                clip=mat_ortho(0, 320, 0, 200, -1000, 1000),
                zoom=1.0, focal=620.0, bg=(0.08, 0.08, 0.10), grid=())
            assert _png.startswith(b"P6\n320 200\n255\n"), _png[:16]
            print("GL_PROBE OK (%d bytes)" % len(_png))
            _v.close()
        except Exception as e:
            print("GL_PROBE FAIL:", type(e).__name__, e)
            sys.exit(1)
    else:
        StudioApp().mainloop()
