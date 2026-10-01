# -*- coding: utf-8 -*-
"""
Carrot Particle Editor — Dear ImGui edition (via Dear PyGui).
Same v1.0 effect format as particle_studio.py (Tk edition): 2D/3D editors,
sim core (pure-Python + optional C++ particle_core), undo/redo, JSON export,
live browser preview server.

Logic reused from particle_studio (defaults / validation / templates /
sim math); only the UI layer is ImGui: sidebar form, drawlist viewport
(replaces tkinter Canvas), file/color dialogs, modal chooser.

Run: python editor/studio_imgui.py
"""
import copy
import json
import math
import os
import random
import sys
import threading
import time
import traceback
import webbrowser
from functools import partial

# Repo layout: this file lives in editor/ next to particle_studio.py;
# the repo root (particle_core.pyd) is added to sys.path when running
# from source. Frozen exe bundles everything, so skip the tweak there.
if not getattr(sys, "frozen", False):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

import dearpygui.dearpygui as dpg

import particle_studio as PS
import mesh_cache

try:
    import raster_view as RV
except Exception:
    RV = None

try:
    import particle_core as _CPP_MOD
    HAS_CPP_CORE = True
except Exception:
    _CPP_MOD = None
    HAS_CPP_CORE = False

BUILD_ID = getattr(PS, "BUILD_ID", "b-imgui") + "-imgui"
APP_VERSION = getattr(PS, "APP_VERSION", "?")

# ---------- ImGui dark theme (matches Tk palette) ----------
BG = (26, 27, 34)
SIDEBAR = (34, 35, 46)
CARD = (38, 39, 51)
INPUT = (20, 21, 28)
TEXT = (232, 232, 238)
MUTED = (154, 154, 173)
ACCENT = (123, 97, 255)
OK = (61, 220, 132)
WARN = (255, 92, 92)
YELLOW = (232, 212, 77)
BLUE = (77, 159, 255)


def hex_to_rgb(col, default=(255, 255, 255)):
    h = (col or "").lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return default


def rgba(col, a=255):
    r, g, b = hex_to_rgb(col)
    return (r, g, b, a)


def _safe_action(fn):
    """Button callbacks must never die silently: log + status on error."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            PS.debug_log("UI-ACTION-EXC", fn.__name__,
                         traceback.format_exc().replace("\n", " | ")[:800])
            APP.set_status(f"Error: {e}", WARN)
    return wrapper

# ================= framework-free simulation =================
class SimEngine:
    """Particle sim ported from StudioApp (no Tkinter): pure-Python tracks
    morph + optional C++ core. Particle layout identical to the Tk edition:
    [x,y,vx,vy,age,c0,c1,s0,s1,life,z,vz,shape,tracks,dx,dy,dz,gx,gy,gz,
     sizeRatio,speedRatio]."""

    TK_MAX_DOTS = 800

    def __init__(self):
        self.parts = []
        self.accum = 0.0
        self.bursted = False
        self.last_t = time.time()
        self._cpp_eng = None
        self._cpp_key = None
        self._cpp_out = None
        self._last_sim_mode = None
        self._rand = random.Random()
        self._seed = 0
        self.trail_hist = {}
        self.emitter_trail = []
        self._trail_t = 0.0

    def seed_sim(self, seed):
        """Deterministic seed (0 = legacy unseeded behavior).

        Nonzero seeds make every spawn draw from a fresh private stream, so
        reloading the same effect replays identically in this renderer.
        """
        self._seed = int(seed or 0)
        if self._seed:
            self._rand.seed(self._seed)
        else:
            self._rand.seed()

    def reset(self):
        self.parts = []
        self.accum = 0.0
        self.bursted = False
        self.last_t = time.time()
        if self._cpp_eng is not None:
            try:
                self._cpp_eng.reset()
            except Exception:
                pass
        self._cpp_key = None
        self._cpp_out = None
        self._last_sim_mode = None
        self.trail_hist = {}
        self.emitter_trail = []
        self._trail_t = 0.0

    # ---- trails history (Python reference; ring-capped per source) ----
    @staticmethod
    def _trail_cfg(em):
        t = (em.get("trails") or {}) if isinstance(em, dict) else {}
        if not PS.trails_active(t):
            return None
        return t

    def _trail_push(self, key, x, y, z, now, cfg):
        """Push a point when minDist/minTime is exceeded (else skip)."""
        try:
            maxp = max(2, int(cfg.get("maxPoints", 32) or 32))
            life = max(0.05, float(cfg.get("lifetime", 1.0) or 0))
            md = max(0.0, float(cfg.get("minDist", 4.0) or 0))
            mt = max(0.0, float(cfg.get("minTime", 0.016) or 0))
        except (ValueError, TypeError):
            return
        hist = self.trail_hist.get(key)
        if hist is None:
            hist = self.trail_hist[key] = []
        if hist:
            lx, ly, lz, lt = hist[-1]
            if mt > 0.0 and (now - lt) < mt:
                return
            dx, dy, dz = x - lx, y - ly, z - lz
            if md > 0.0 and (dx * dx + dy * dy + dz * dz) < md * md:
                return
        hist.append((x, y, z, now))
        while len(hist) > maxp:
            hist.pop(0)
        while len(hist) > 1 and (now - hist[0][3]) > life:
            hist.pop(0)

    # ---- keyframe tracks (identical semantics to particle_studio) ----
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

    @staticmethod
    def _build_tracks(states, ptype):
        tracks = []
        prev_shape = None
        ok_shapes = PS.SHAPES_3D if ptype == "3d" else PS.SHAPES_2D
        fallback = "sphere" if ptype == "3d" else "circle"
        for s in states:
            ap = s.get("appearance", {})
            mv = s.get("movement", {})
            shp = str(s.get("shape", "") or "").lower() or prev_shape
            shp = shp if shp in ok_shapes else fallback
            prev_shape = shp or fallback
            tracks.append({
                "dur": max(1e-6, float(s.get("duration", 0.5) or 0.5)),
                "shape": prev_shape,
                "size": float(ap.get("size", 8) or 0),
                "sizeMax": float(ap.get("sizeMax", ap.get("size", 8)) or 0),
                "color": ap.get("color", "#ffffff") or "#ffffff",
                "opacity": float(ap.get("opacity", 255)
                                 if ap.get("opacity") is not None else 255),
                "minSpd": float(mv.get("minSpeed", 0) or 0),
                "maxSpd": float(mv.get("maxSpeed", mv.get("minSpeed", 0)) or 0),
                "easing": s.get("easing", "linear") or "linear",
            })
        return tracks

    @classmethod
    def _locate(cls, tracks, age):
        segs = max(1, len(tracks) - 1)
        total = sum(tracks[k]["dur"] for k in range(segs))
        t = max(0.0, min(age, total)) if total > 0 else 0.0
        acc = 0.0
        for k in range(segs):
            d = tracks[k]["dur"]
            if t < acc + d or k == segs - 1:
                raw = 0.0 if d <= 0 else max(0.0, min(1.0, (t - acc) / d))
                return k, cls._ease_fn(raw, tracks[k]["easing"]), raw
            acc += d
        return segs - 1, 1.0, 1.0

    # Shape cross-fade window around the mid-segment flip point. Inside
    # (0.25, 0.75) of raw segment time the next keyframe's shape fades in
    # while the current one fades out (mirrors the C++ core, which reports
    # the same window per particle as (bseg, bt)).
    BLEND_LO = 0.25
    BLEND_HI = 0.75

    @staticmethod
    def blend_window(tracks, age):
        """(seg, t) morph companion, or (-1, 0.0) outside the window."""
        if len(tracks) < 2:
            return -1, 0.0
        k, _e, raw = SimEngine._locate(tracks, age)
        if SimEngine.BLEND_LO < raw < SimEngine.BLEND_HI:
            return k, ((raw - SimEngine.BLEND_LO)
                       / (SimEngine.BLEND_HI - SimEngine.BLEND_LO))
        return -1, 0.0

    @staticmethod
    def _lerp_color(c0, c1, t):
        a, b = hex_to_rgb(c0), hex_to_rgb(c1)
        return "#%02x%02x%02x" % (round(a[0] + (b[0] - a[0]) * t),
                                  round(a[1] + (b[1] - a[1]) * t),
                                  round(a[2] + (b[2] - a[2]) * t))

    @classmethod
    def sample_tracks(cls, tracks, age, sizeRatio, speedRatio):
        k, e, raw = cls._locate(tracks, age)
        a, b = tracks[k], tracks[min(k + 1, len(tracks) - 1)]
        smin = a["size"] + (b["size"] - a["size"]) * e
        smax = a["sizeMax"] + (b["sizeMax"] - a["sizeMax"]) * e
        mn = a["minSpd"] + (b["minSpd"] - a["minSpd"]) * e
        mx = a["maxSpd"] + (b["maxSpd"] - a["maxSpd"]) * e
        return {
            "size": smin + (smax - smin) * sizeRatio,
            "color": cls._lerp_color(a["color"], b["color"], e),
            "opacity": a["opacity"] + (b["opacity"] - a["opacity"]) * e,
            "speed": mn + (mx - mn) * speedRatio,
            "shape": b["shape"] if raw >= 0.5 else a["shape"],
        }

    @staticmethod
    def _cone_dir3(rand, bx, by, bz, spread_deg):
        n = math.sqrt(bx * bx + by * by + bz * bz) or 1.0
        bx, by, bz = bx / n, by / n, bz / n
        ux, uy, uz = (0.0, 1.0, 0.0) if abs(by) < 0.95 else (1.0, 0.0, 0.0)
        cx1, cy1, cz1 = (by * uz - bz * uy, bz * ux - bx * uz, bx * uy - by * ux)
        n1 = math.sqrt(cx1 * cx1 + cy1 * cy1 + cz1 * cz1) or 1.0
        ux, uy, uz = cx1 / n1, cy1 / n1, cz1 / n1
        vx, vy, vz = by * uz - bz * uy, bz * ux - bx * uz, bx * uy - by * ux
        a = rand.random() * math.pi * 2
        r = math.tan(math.radians(spread_deg / 2)) * math.sqrt(rand.random())
        dx = bx + (ux * math.cos(a) + vx * math.sin(a)) * r
        dy = by + (uy * math.cos(a) + vy * math.sin(a)) * r
        dz = bz + (uz * math.cos(a) + vz * math.sin(a)) * r
        n2 = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        return (dx / n2, dy / n2, dz / n2)

    def spawn(self, em, ptype, cx, cy, emitter_pos, tracks):
        cone = em.get("propagationCone", {})
        zone = em.get("emissionZone", {})
        is3d = "directionZ" in cone
        spread = cone.get("spread", 90)
        jitter = 0.9 + self._rand.random() * 0.2
        for tr in tracks:
            tr["dur"] *= jitter
        life = max(0.1, sum(tr["dur"] for tr in tracks[:-1]))
        sizeRatio, speedRatio = self._rand.random(), self._rand.random()
        head = self.sample_tracks(tracks, 0.0, sizeRatio, speedRatio)
        spd0 = head["speed"]
        if is3d:
            zshape = str(zone.get("shape", "sphere"))
            rot3 = math.radians(zone.get("rotationZ", zone.get("rotation", 0)) or 0)
            cr3, sr3 = math.cos(rot3), math.sin(rot3)
            if zshape == "sphere":
                th = self._rand.random() * math.pi * 2
                ph = math.acos(2 * self._rand.random() - 1)
                rr = (zone.get("radius", 10) or 10) * (self._rand.random() ** (1 / 3))
                sx = rr * math.sin(ph) * math.cos(th)
                sy = rr * math.cos(ph)
                sz = rr * math.sin(ph) * math.sin(th)
            elif zshape == "box":
                sx = (self._rand.random() - 0.5) * (zone.get("width", 100) or 100)
                sy = (self._rand.random() - 0.5) * (zone.get("height", 60) or 60)
                sz = (self._rand.random() - 0.5) * (zone.get("depth", 60) or 60)
                sx, sy = sx * cr3 - sy * sr3, sx * sr3 + sy * cr3
            elif zshape == "line":
                sx = (self._rand.random() - 0.5) * (zone.get("length", 100) or 100)
                sy, sz = 0.0, 0.0
                sx, sy = sx * cr3 - sy * sr3, sx * sr3 + sy * cr3
            else:
                sx, sy, sz = 0.0, 0.0, 0.0
            az = math.radians(cone.get("directionZ", 0))
            el = math.radians(cone.get("directionY", 0))
            base = (math.cos(el) * math.cos(az), math.sin(el),
                    math.cos(el) * math.sin(az))
            dx, dy, dz = self._cone_dir3(self._rand, base[0], base[1], base[2], spread)
            ex, ey, ez = emitter_pos
            if em.get("reverse"):
                dist = spd0 * life
                return [ex + sx + dx * dist, ey + sy + dy * dist,
                        -dx * spd0, -dy * spd0, 0.0, "", "", 0, 0, life,
                        ez + sz + dz * dist, -dz * spd0, head["shape"],
                        tracks, -dx, -dy, -dz, 0.0, 0.0, 0.0,
                        sizeRatio, speedRatio]
            return [ex + sx, ey + sy, dx * spd0, dy * spd0, 0.0, "", "", 0, 0,
                    life, ez + sz, dz * spd0, head["shape"],
                    tracks, dx, dy, dz, 0.0, 0.0, 0.0, sizeRatio, speedRatio]
        ang = math.radians(cone.get("direction", 0) +
                           self._rand.uniform(-spread / 2, spread / 2))
        zshape = str(zone.get("shape", "Circle")).lower()
        rot = math.radians(zone.get("rotation", 0) or 0)
        zmode = str(zone.get("mode", "Surface")).lower()
        lx, ly = 0.0, 0.0
        if zshape == "circle":
            rr = zone.get("radius", 50) or 50
            a = self._rand.random() * math.pi * 2
            if zmode == "edge":
                lx, ly = math.cos(a) * rr, math.sin(a) * rr
            else:
                r = math.sqrt(self._rand.random()) * rr
                lx, ly = math.cos(a) * r, math.sin(a) * r
        elif zshape == "rectangle":
            w, h = (zone.get("width", 100) or 100), (zone.get("height", 60) or 60)
            if zmode == "edge":
                per = 2 * (w + h)
                d = self._rand.random() * per
                if d < w:
                    lx, ly = d - w / 2, -h / 2
                elif d < w + h:
                    lx, ly = w / 2, (d - w) - h / 2
                elif d < 2 * w + h:
                    lx, ly = w / 2 - (d - w - h), h / 2
                else:
                    lx, ly = -w / 2, h / 2 - (d - 2 * w - h)
            else:
                lx, ly = (self._rand.random() - 0.5) * w, (self._rand.random() - 0.5) * h
        elif zshape == "line":
            lx = (self._rand.random() - 0.5) * (zone.get("length", 100) or 100)
        ox = lx * math.cos(rot) - ly * math.sin(rot)
        oy = lx * math.sin(rot) + ly * math.cos(rot)
        dx, dy = math.cos(ang), math.sin(ang)
        if em.get("reverse"):
            dist = spd0 * life
            return [cx + ox + dx * dist, cy + oy + dy * dist,
                    -dx * spd0, -dy * spd0, 0.0, "", "", 0, 0, life,
                    0.0, 0.0, head["shape"],
                    tracks, -dx, -dy, 0.0, 0.0, 0.0, 0.0,
                    sizeRatio, speedRatio]
        return [cx + ox, cy + oy, dx * spd0, dy * spd0, 0.0, "", "", 0, 0,
                life, 0.0, 0.0, head["shape"],
                tracks, dx, dy, 0.0, 0.0, 0.0, 0.0, sizeRatio, speedRatio]

    def step_py(self, em, ptype, cx, cy, emitter_pos, cam, tracks, dt, maxp):
        g = em.get("gravity", {})
        gx = g.get("y", 0) * dt * 0.4
        gy = g.get("x", 0) * dt * 0.4
        gz = g.get("z", 0) * dt * 0.4
        fld = em.get("fields")
        fld_on = PS.fields_active(fld)
        flat = (ptype != "3d")
        ex, ey, ez = emitter_pos
        col = (fld.get("collision") or {}) if isinstance(fld, dict) else {}
        try:
            planeY = col.get("planeY")
            planeY = float(planeY) if planeY is not None else None
        except (ValueError, TypeError):
            planeY = None
        bounce = float(col.get("bounce", 0.5) or 0.0)
        friction = float(col.get("friction", 0.1) or 0.0)
        plane_on = planeY is not None
        mode = em.get("mode", "Infinite")
        if mode != self._last_sim_mode:
            self._last_sim_mode = mode
            self.parts = []
            self.accum = 0.0
            self.bursted = False
        if mode == "Burst":
            if not self.bursted:
                for _ in range(min(maxp, 150)):
                    self.parts.append(
                        self.spawn(em, ptype, cx, cy, emitter_pos,
                                   copy.deepcopy(tracks)))
                self.bursted = True
        else:
            flow = float(em.get("flow", 40) or 40)
            self.accum += flow * dt
            while self.accum >= 1 and len(self.parts) < maxp:
                self.accum -= 1
                self.parts.append(
                    self.spawn(em, ptype, cx, cy, emitter_pos,
                               copy.deepcopy(tracks)))
        for p in self.parts:
            p[17] += gx
            p[18] += gy
            p[19] += gz
            if fld_on:
                ax, ay, az = PS.field_accel(p[0], p[1], p[10], p[4], fld,
                                            ex, ey, ez, flat)
                p[17] += ax * dt
                p[18] += ay * dt
                p[19] += az * dt
            smp = self.sample_tracks(p[13], p[4], p[20], p[21])
            p[2] = p[14] * smp["speed"] + p[17]
            p[3] = p[15] * smp["speed"] + p[18]
            p[11] = p[16] * smp["speed"] + p[19]
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[10] += p[11] * dt
            p[4] += dt
            if plane_on and p[1] < planeY:
                # bounce via the gravity accumulator (velocities are rebuilt
                # from dir*speed each frame, so impulses must persist there)
                p[1] = planeY
                p[17] += p[2] * -friction
                p[18] += -p[3] * (1.0 + bounce)
                p[19] += p[11] * -friction
        if len(self.parts) > maxp or (self.parts and self.parts[0][4] >= self.parts[0][9]):
            self.parts = [p for p in self.parts if p[4] < p[9]][-maxp:]
        tcfg = self._trail_cfg(em)
        if tcfg is not None:
            self._trail_t += dt
            now = self._trail_t
            if str(tcfg.get("source", "particles")) == "emitter":
                self._trail_push("emitter", ex, ey, ez, now, tcfg)
                self.trail_hist = {"emitter": self.trail_hist.get("emitter", [])}
            else:
                alive = set()
                for p in self.parts:
                    key = id(p)
                    alive.add(key)
                    self._trail_push(key, p[0], p[1], p[10], now, tcfg)
                for k in list(self.trail_hist.keys()):
                    if k != "emitter" and k not in alive:
                        del self.trail_hist[k]
        elif self.trail_hist:
            self.trail_hist = {}
        return len(self.parts)

    def step_cpp(self, eff, em, ptype, tracks, is3d, dt, scx, scy,
                 emitter_pos, cam, focal, cx, cy, gx, gy, gz, maxp, cache_key):
        """Advance the optional C++ core. Returns count or raises (caller
        falls back to pure-Python)."""
        if self._cpp_eng is None:
            self._cpp_eng = _CPP_MOD.Engine()
            self._cpp_eng.set_seed(random.randrange(1 << 30))
            self._cpp_key = None
        if cache_key != self._cpp_key:
            self._cpp_eng.configure(eff["emitter"], tracks, is3d)
            self._cpp_key = cache_key
        ex, ey, ez = emitter_pos
        out = self._cpp_eng.step(dt, scx, scy, ex, ey, ez, gx, gy, gz, maxp,
                                 cam["yaw"], cam["pitch"], cam["zoom"],
                                 cam["ox"], cam["oy"], focal, cx, cy)
        self._cpp_out = out
        return len(out["x"])

# ================= application state =================
class App:
    def __init__(self):
        self.ptype = "2d"
        self.trail = False
        self.editor_mode = "2d"
        self.filename = "Default"
        self.filepath = None
        self.states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
        self.sel_state = 0
        self.em = PS.default_emitter("2d")
        self.cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0,
                    "ox": 0.0, "oy": 0.0, "focal": 620.0}
        self.emitter_pos = [0.0, 0.0, 0.0]
        self.emitter2d = [0.0, 0.0]
        self.fov = 60.0
        self.sens = 1.0
        self.glow = True
        self.colormode = "gradient"  # or "selected"
        self.sim = SimEngine()
        self._history = []
        self._hidx = -1
        self._restoring = False
        self._dirty = True
        self._cache_t = 0.0
        self._cached_eff = None
        self._last_edit = 0.0
        self._models_fp = None
        self._live_push_on = False
        self._last_push = 0.0
        self._status = "Ready"
        self._status_col = OK
        self._fps = 60
        self._n_show = 0
        self._cpp_active = False
        self._gizmo = None
        self._drag = None
        self._wheel = 0
        self._dblclick = False
        self._custom_nodes = []
        self._editor_open = False

    # ---------- projection / camera (same math as Tk edition) ----------
    def proj(self, x, y, z, cx, cy):
        syaw, cyaw = math.sin(self.cam["yaw"]), math.cos(self.cam["yaw"])
        spit, cpit = math.sin(self.cam["pitch"]), math.cos(self.cam["pitch"])
        x1 = x * cyaw + z * syaw
        z1 = -x * syaw + z * cyaw
        y2 = y * cpit - z1 * spit
        z2 = y * spit + z1 * cpit
        f = self.cam.get("focal", 620.0)
        scale = self.cam["zoom"] * f / (f + z2)
        return (cx + self.cam["ox"] + x1 * scale,
                cy + self.cam["oy"] - y2 * scale, scale, z2)

    # ---------- effect assembly (mirrors StudioApp.current_effect) ----------
    @staticmethod
    def _fnum(v, default=0.0):
        try:
            f = float(v)
        except (ValueError, TypeError):
            return default
        return f if math.isfinite(f) else default

    def _read_fields(self, f):
        """Sanitized fields block (None planeY stays None = disabled)."""
        d = PS.default_fields()
        if isinstance(f, dict):
            for k in ("turbulence", "vortex", "attractor", "collision"):
                if isinstance(f.get(k), dict):
                    d[k].update(f[k])
        F = self._fnum
        t, v, a, c = d["turbulence"], d["vortex"], d["attractor"], d["collision"]
        py = c.get("planeY")
        try:
            py = float(py) if py is not None else None
        except (ValueError, TypeError):
            py = None
        return {
            "turbulence": {"amount": F(t.get("amount", 0), 0),
                           "scale": F(t.get("scale", 0.05), 0.05),
                           "speed": F(t.get("speed", 1.0), 1.0)},
            "vortex": {"strength": F(v.get("strength", 0), 0)},
            "attractor": {"x": F(a.get("x", 0), 0), "y": F(a.get("y", 0), 0),
                          "z": F(a.get("z", 0), 0),
                          "strength": F(a.get("strength", 0), 0),
                          "radius": max(0.0, F(a.get("radius", 200), 200))},
            "collision": {"planeY": py, "bounce": F(c.get("bounce", 0.5), 0.5),
                          "friction": F(c.get("friction", 0.1), 0.1)},
        }

    def _read_trails(self, t):
        """Sanitized trails block (off by default = legacy look)."""
        d = PS.default_trails()
        if isinstance(t, dict):
            for k, v in t.items():
                if k in d:
                    d[k] = v
        F = self._fnum
        src = str(d.get("source", "particles")).lower()
        uv = str(d.get("uvMode", d.get("uvMode", "stretch"))).lower()
        rib = str(d.get("ribbon", "billboard")).lower()
        return {
            "enabled": bool(d.get("enabled", False)),
            "source": src if src in ("particles", "emitter") else "particles",
            "maxPoints": max(2, int(F(d.get("maxPoints", 32), 32))),
            "lifetime": max(0.05, F(d.get("lifetime", 1.0), 1.0)),
            "minDist": max(0.0, F(d.get("minDist", 4.0), 4.0)),
            "minTime": max(0.0, F(d.get("minTime", 0.016), 0.016)),
            "smoothing": max(0, int(F(d.get("smoothing", 0), 0))),
            "widthStart": max(0.0, F(d.get("widthStart", 8.0), 8.0)),
            "widthEnd": max(0.0, F(d.get("widthEnd", 1.0), 1.0)),
            "taper": F(d.get("taper", 1.0), 1.0),
            "uvMode": uv if uv in ("stretch", "tile") else "stretch",
            "tileLength": max(1.0, F(d.get("tileLength", 64.0), 64.0)),
            "ribbon": rib if rib in ("billboard", "fixed", "flat") else "billboard",
            "colorHead": str(d.get("colorHead", "#ffffff") or "#ffffff"),
            "colorTail": str(d.get("colorTail", "#ffffff") or "#ffffff"),
            "alphaHead": max(0, min(255, int(F(d.get("alphaHead", 255), 255)))),
            "alphaTail": max(0, min(255, int(F(d.get("alphaTail", 0), 0)))),
            "blend": str(d.get("blend", "inherit") or "inherit"),
            "gravity": F(d.get("gravity", 0.0), 0.0),
            "drag": max(0.0, F(d.get("drag", 0.0), 0.0)),
            "noise": max(0.0, F(d.get("noise", 0.0), 0.0)),
        }

    def read_emitter(self):
        """Rebuild a type-correct emitter dict every read (like the Tk
        edition): switching 2D<->3D never leaks the other mode's keys,
        so spawn/export always match the ACTIVE editor."""
        src = self.em if isinstance(self.em, dict) else {}
        g = src.get("gravity", {}) or {}
        z = src.get("emissionZone", {}) or {}
        c = src.get("propagationCone", {}) or {}
        F = self._fnum
        flow = max(0.0, F(src.get("flow", 40), 40))
        maxp = max(1, int(F(src.get("maxParticles", 300), 300)))
        resv = max(0, int(F(src.get("reservoir", 50), 50)))
        mode = str(src.get("mode", "Infinite"))
        rev = bool(src.get("reverse", False))
        ali = bool(src.get("alignDir", False))
        fields = self._read_fields(src.get("fields"))
        trails = self._read_trails(src.get("trails"))
        if self.ptype == "3d":
            zs = str(z.get("shape", "sphere") or "sphere").lower()
            if zs not in PS.ZONE_3D:
                zs = "sphere"
            return {
                "flow": flow, "flowMode": "rate", "flowInterval": 1,
                "maxParticles": maxp, "reservoir": resv,
                "mode": mode, "reverse": rev, "alignDir": ali,
                "billboard": True, "rotationMode": "speed",
                "gravity": {"x": F(g.get("x", 0)), "y": F(g.get("y", 0)),
                            "z": F(g.get("z", 0))},
                "emissionZone": {
                    "shape": zs,
                    "radius": max(0.0, F(z.get("radius", 10), 10)),
                    "width": max(0.0, F(z.get("width", 100), 100)),
                    "height": max(0.0, F(z.get("height", 60), 60)),
                    "depth": max(0.0, F(z.get("depth", 60), 60)),
                    "length": max(0.0, F(z.get("length", 100), 100)),
                    "mode": str(z.get("mode", "Surface")),
                    "rotationX": 0, "rotationY": 0,
                    "rotationZ": F(z.get("rotationZ", z.get("rotation", 0))),
                    "showZone": bool(z.get("showZone", True))},
                "propagationCone": {
                    "directionX": 0,
                    "directionY": F(c.get("directionY", 0)),
                    "directionZ": F(c.get("directionZ",
                                          c.get("direction", 0))),
                    "spread": max(0.0, min(360.0, F(c.get("spread", 90),
                                                    90))),
                    "showCone": bool(c.get("showCone", True))},
                "blendingMode": (src.get("blendingMode") if src.get("blendingMode") in PS.BLEND_MODES else "Normal"),
                "seed": int(src.get("seed", 0) or 0),
                "fields": fields,
                "trails": trails,
            }
        zs = str(z.get("shape", "Circle") or "Circle")
        if zs not in PS.ZONE_2D:
            zs = "Circle"
        return {
            "flow": flow, "flowMode": "rate", "flowInterval": 1,
            "maxParticles": maxp, "reservoir": resv,
            "mode": mode, "reverse": rev, "alignDir": ali,
            "rotationMode": "speed",
            "gravity": {"x": F(g.get("x", 0)), "y": F(g.get("y", 0))},
            "emissionZone": {
                "shape": zs,
                "rotation": F(z.get("rotation", z.get("rotationZ", 0))),
                "radius": max(0.0, F(z.get("radius", 10), 10)),
                "width": max(0.0, F(z.get("width", 100), 100)),
                "height": max(0.0, F(z.get("height", 60), 60)),
                "length": max(0.0, F(z.get("length", 100), 100)),
                "mode": str(z.get("mode", "Surface")),
                "showZone": bool(z.get("showZone", True))},
            "propagationCone": {
                "direction": F(c.get("direction", c.get("directionZ", 0))),
                "spread": max(0.0, min(360.0, F(c.get("spread", 90), 90))),
                "showCone": bool(c.get("showCone", True))},
            "blendingMode": (src.get("blendingMode") if src.get("blendingMode") in PS.BLEND_MODES else "Normal"),
            "seed": int(src.get("seed", 0) or 0),
            "fields": fields,
            "trails": trails,
        }

    def current_effect(self):
        em = self.read_emitter()
        states = []
        for s in self.states:
            ns = json.loads(json.dumps(s))
            shp = str(ns.get("shape", "") or "").lower()
            if self.ptype == "3d":
                ns["shape"] = shp if shp in PS.SHAPES_3D else "sphere"
                mv = ns.get("movement", {})
                zmin = mv.get("minRot", mv.get("minRotZ", 0))
                zmax = mv.get("maxRot", mv.get("maxRotZ", 0))
                mv.update({"minRotX": 0, "maxRotX": 0, "minRotY": 0,
                           "maxRotY": 0, "minRotZ": zmin, "maxRotZ": zmax})
                mv.pop("minRot", None)
                mv.pop("maxRot", None)
                ns["movement"] = mv
            else:
                ns["shape"] = shp if shp in PS.SHAPES_2D else "circle"
            ns.pop("customModel", None)
            states.append(ns)
        eff = PS.build_effect(self.ptype, em, states)
        if self.ptype == "3d":
            block = PS.effect_models_block(self.states, states)
            if block is not None:
                eff["models"] = block
        return eff

    def cached_effect(self):
        now = time.time()
        if self._cached_eff is None or self._dirty or now - self._cache_t > 0.15:
            try:
                self._cached_eff = self.current_effect()
            except Exception:
                self._cached_eff = None
            self._cache_t = now
            self._dirty = False
        return self._cached_eff

    def mark_dirty(self):
        self._dirty = True
        self._last_edit = time.time()

    # ---------- undo / redo ----------
    def snapshot(self):
        return {"ptype": self.ptype, "trail": bool(getattr(self, "trail", False)),
                "editor_mode": getattr(self, "editor_mode", self.ptype),
                "filename": self.filename,
                "emitter": copy.deepcopy(self.em),
                "states": copy.deepcopy(self.states),
                "sel": self.sel_state,
                "cam": {k: self.cam[k] for k in ("yaw", "pitch", "zoom", "ox", "oy")},
                "emitter_pos": list(self.emitter_pos),
                "emitter2d": list(self.emitter2d),
                "fov": self.fov}

    def history_commit(self):
        if self._restoring:
            return
        snap = self.snapshot()
        key = json.dumps(snap, sort_keys=True, ensure_ascii=False)
        if self._history and self._history[self._hidx][0] == key:
            return
        del self._history[self._hidx + 1:]
        self._history.append((key, snap))
        if len(self._history) > 100:
            self._history.pop(0)
        self._hidx = len(self._history) - 1

    def history_restore(self, snap):
        self._restoring = True
        try:
            self.ptype = snap["ptype"]
            self.trail = bool(snap.get("trail", False))
            self.editor_mode = snap.get("editor_mode",
                                        "trail2d" if self.trail and self.ptype == "2d"
                                        else "trail3d" if self.trail
                                        else self.ptype)
            self.filename = snap.get("filename", "Default")
            self.em = copy.deepcopy(snap["emitter"])
            self.states = copy.deepcopy(snap["states"])
            self.sel_state = max(0, min(snap.get("sel", 0), len(self.states) - 1))
            self.cam.update(snap.get("cam", {}))
            self.emitter_pos = list(snap.get("emitter_pos", (0.0, 0.0, 0.0)))
            self.emitter2d = list(snap.get("emitter2d", (0.0, 0.0)))
            self.fov = snap.get("fov", 60.0)
            self.sync_state_form()
            self.sim.reset()
        finally:
            self._restoring = False

    def undo(self):
        self.history_commit()
        if self._hidx > 0:
            self._hidx -= 1
            self.history_restore(self._history[self._hidx][1])
            self.set_status("Undo", MUTED)

    def redo(self):
        if self._hidx < len(self._history) - 1:
            self._hidx += 1
            self.history_restore(self._history[self._hidx][1])
            self.set_status("Redo", MUTED)

    def set_status(self, text, col=OK):
        self._status = text
        self._status_col = col
        try:
            dpg.set_value("status_text", text)
            dpg.configure_item("status_text", color=list(col) + [255])
        except Exception:
            pass


# ================= viewport (drawlist replaces tkinter Canvas) =================
def _c(col, a=255):
    r, g, b = hex_to_rgb(col)
    return [r, g, b, a]


def _poly_points(shape, x, y, r):
    kind, pay = PS.StudioApp._poly_2d(shape, x, y, r)
    if kind == "rect":
        x0, y0, x1, y1 = pay
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if kind == "poly":
        return [(pay[i], pay[i + 1]) for i in range(0, len(pay), 2)]
    if kind == "line":
        return None
    x0, y0, x1, y1 = pay
    return ("oval", (x0, y0, x1, y1))


def draw_shape_2d(dl, x, y, r, shape, col, glow_col=None, thick=1):
    pts = _poly_points(shape, x, y, r)
    if glow_col is not None:
        hr = r * 2.2
        dpg.draw_circle([x, y], hr, color=[0, 0, 0, 0], fill=glow_col,
                        parent=dl, segments=20)
    if pts is None:  # line
        dpg.draw_line([x - r * 1.6, y], [x + r * 1.6, y], color=col,
                      thickness=max(2, int(r * 0.5)), parent=dl)
    elif isinstance(pts, tuple):  # oval / hollow
        kind, (x0, y0, x1, y1) = pts
        cx, cy, rr = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
        if shape == "custom":
            dpg.draw_circle([cx, cy], rr, color=col, thickness=2, parent=dl,
                            segments=24)
        else:
            dpg.draw_circle([cx, cy], rr, color=[0, 0, 0, 0], fill=col,
                            parent=dl, segments=24)
    else:
        dpg.draw_polygon(pts, color=[0, 0, 0, 0], fill=col, parent=dl)


def draw_shape_3d(dl, sx, sy, r, shape, col):
    dark = list(hex_to_rgb(PS.StudioApp._lerp_color(
        "#%02x%02x%02x" % tuple(col[:3]), "#000000", 0.35))) + [255]
    if shape == "cube":
        h = r * 0.9
        o = h * 0.45
        dpg.draw_polygon([[sx - h + o, sy - h - o], [sx + h + o, sy - h - o],
                          [sx + h, sy - h], [sx - h, sy - h]],
                         color=[0, 0, 0, 0], fill=dark, parent=dl)
        dpg.draw_rectangle([sx - h, sy - h], [sx + h, sy + h],
                           color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape == "pyramid":
        dpg.draw_polygon([[sx - r, sy + r * 0.7], [sx + r, sy + r * 0.7],
                          [sx + r * 0.5, sy + r * 0.2],
                          [sx - r * 0.5, sy + r * 0.2]],
                         color=[0, 0, 0, 0], fill=dark, parent=dl)
        dpg.draw_polygon([[sx, sy - r], [sx + r, sy + r * 0.7],
                          [sx - r, sy + r * 0.7]],
                         color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape == "torus":
        dpg.draw_circle([sx, sy], r, color=[0, 0, 0, 0], fill=col, parent=dl,
                        segments=24)
        dpg.draw_circle([sx, sy], r * 0.45, color=[0, 0, 0, 0],
                        fill=[20, 21, 28, 255], parent=dl, segments=20)
    elif shape == "diamond":
        dpg.draw_polygon([[sx, sy - r], [sx + r * 0.7, sy], [sx, sy + r],
                          [sx - r * 0.7, sy]],
                         color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape in ("square", "billboard"):
        dpg.draw_rectangle([sx - r, sy - r], [sx + r, sy + r],
                           color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape == "triangle":
        dpg.draw_polygon([[sx, sy - r], [sx + r, sy + r * 0.8],
                          [sx - r, sy + r * 0.8]],
                         color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape == "star":
        _, pay = PS.StudioApp._poly_2d("star", sx, sy, r)
        pts = [(pay[i], pay[i + 1]) for i in range(0, len(pay), 2)]
        dpg.draw_polygon(pts, color=[0, 0, 0, 0], fill=col, parent=dl)
    elif shape == "line":
        dpg.draw_line([sx - r * 1.6, sy], [sx + r * 1.6, sy], color=col,
                      thickness=max(2, int(r * 0.5)), parent=dl)
    elif shape == "custom":
        dpg.draw_rectangle([sx - r, sy - r], [sx + r, sy + r], color=col,
                           thickness=2, parent=dl)
    else:
        dpg.draw_circle([sx, sy], r, color=[0, 0, 0, 0], fill=col, parent=dl,
                        segments=24)


MESH_MAX_PARTICLES = 120  # above this, custom meshes fall back to the box
MESH_FRAME_BUDGET = 1500  # max mesh polygons per frame (adaptive LOD)
MESH_MIN_R = 3.0  # smaller on-screen customs fall back to the box


def _find_model_file(base):
    """Resolve a stored model basename against likely locations."""
    if not base:
        return ""
    cands = [os.path.join(os.getcwd(), base),
             os.path.join(PS.app_base_dir(), base),
             os.path.join(PS.app_base_dir(), "assets", base)]
    for p in cands:
        try:
            if os.path.isfile(p):
                return p
        except Exception:
            pass
    return ""


def state_model_ref(s):
    """Model ref for a state (matches current_effect()'s convention)."""
    try:
        cm = s.get("customModel") or {}
        return (str((s.get("modelRefs") or [""])[0] or "")
                or str(cm.get("node") or ""))
    except Exception:
        return ""


def _iter_custom_meshes(states):
    """Yield (ref, tris, texels, culls) for custom states with models."""
    for s in states or []:
        try:
            if str(s.get("shape", "")).lower() != "custom":
                continue
            cm = s.get("customModel") or {}
            path = cm.get("path") or ""
            if not path:
                path = _find_model_file(cm.get("file") or "")
            if not path:
                continue
            tris, texels, culls = mesh_cache.load_mesh(path,
                                                       cm.get("node") or "")
            if not tris:
                continue
            yield state_model_ref(s), tris, texels, culls
        except Exception:
            continue


def custom_mesh():
    """(normalized tris, per-tri material (r,g,b), per-tri cullable).

    Nones when no model resolves. Prefers the selected state, else the
    first custom-shaped state carrying a model. Never mutates APP.
    """
    states = APP.states
    if 0 <= APP.sel_state < len(states):
        ordered = [states[APP.sel_state]]
        ordered.extend(s for s in states if
                       not any(s is o for o in ordered))
    else:
        ordered = list(states)
    for _ref, tris, texels, culls in _iter_custom_meshes(ordered):
        return tris, texels, culls
    return None, None, None


def custom_mesh_tris():
    """Normalized mesh triangles or None (see custom_mesh)."""
    tris, _tex, _cull = custom_mesh()
    return tris


def _mesh_projector(app, cx, cy):
    """Camera projector with trig hoisted (screen map of App.proj)."""
    cam = app.cam
    syaw, cyaw = math.sin(cam["yaw"]), math.cos(cam["yaw"])
    spit, cpit = math.sin(cam["pitch"]), math.cos(cam["pitch"])
    zoom = cam["zoom"]
    focal = cam.get("focal", 620.0)
    ox, oy = cam["ox"], cam["oy"]

    def proj(wx, wy, wz, lx, ly, lz, ws):
        x = wx + lx * ws
        y = wy + ly * ws
        z = wz + lz * ws
        x1 = x * cyaw + z * syaw
        z1 = -x * syaw + z * cyaw
        y2 = y * cpit - z1 * spit
        z2 = y * spit + z1 * cpit
        sc = zoom * focal / (focal + z2)
        return (cx + ox + x1 * sc, cy + oy - y2 * sc, z2)

    return proj


def _lod_tris(tris, texels, culls, n_total):
    keep = max(8, MESH_FRAME_BUDGET // max(1, int(n_total)))
    if len(tris) <= keep:
        return tris, texels, culls
    step = len(tris) / keep
    idx = [int(i * step) for i in range(keep)]
    return ([tris[i] for i in idx], [texels[i] for i in idx],
            [culls[i] for i in idx])
def mesh_frame(app, cx, cy, n_total):
    """Frame-hoisted custom-mesh data: (tris, texels, culls, proj) or None.

    Resolves the preferred mesh once and stride-downsamples it to the
    frame polygon budget (see frame_meshes() for the multi-ref variant).
    """
    tris, texels, culls = custom_mesh()
    if not tris:
        return None
    tris, texels, culls = _lod_tris(tris, texels, culls, n_total)
    return (tris, texels, culls, _mesh_projector(app, cx, cy))


def frame_meshes(app, cx, cy, n_total):
    """({ref: (tris, texels, culls)}, proj) for custom states with models.

    One entry per model ref (LOD applied); (None, None) when nothing
    resolves. Used by the morph renderer so each blend side draws its
    own mesh.
    """
    entries = {}
    for ref, tris, texels, culls in _iter_custom_meshes(app.states):
        if ref not in entries:
            entries[ref] = _lod_tris(tris, texels, culls, n_total)
    if not entries:
        return None, None
    return entries, _mesh_projector(app, cx, cy)


def draw_custom_mesh_3d(dl, mesh_data, wx, wy, wz, ws_world, col):
    """Draw one particle as its uploaded mesh, camera-projected.

    mesh_data comes from mesh_frame() (frame-hoisted). Each triangle is
    filled with its material color; the particle color acts as a tint
    (white = natural materials). Triangles are painter-sorted far to
    near and single-sided backfaces are culled, so closed meshes read
    as solids instead of a scrambled blob. ws_world is the mesh
    half-extent in world units. Returns True when drawn, False to fall
    back to the box.
    """
    if mesh_data is None or ws_world <= 0:
        return False
    try:
        tris, texels, culls, proj = mesh_data
        tr, tg, tb = (int(col[0]), int(col[1]), int(col[2]))
        a = max(0, min(255, int(col[3])))
        natural = (tr == 255 and tg == 255 and tb == 255)
        poly = dpg.draw_polygon
        items = []
        for tri, (mr, mg, mb), cull in zip(tris, texels, culls):
            (ax, ay, az), (bx, by, bz), (cx_, cy_, cz_) = tri
            x0, y0, z0 = proj(wx, wy, wz, ax, ay, az, ws_world)
            x1, y1, z1 = proj(wx, wy, wz, bx, by, bz, ws_world)
            x2, y2, z2 = proj(wx, wy, wz, cx_, cy_, cz_, ws_world)
            if cull and (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) >= 0:
                continue  # backface in screen space (y-down)
            if natural:
                fill = [mr, mg, mb, a]
            else:
                fill = [mr * tr // 255, mg * tg // 255, mb * tb // 255, a]
            items.append(((z0 + z1 + z2) / 3.0, [[x0, y0], [x1, y1],
                                                 [x2, y2]], fill))
        items.sort(key=lambda t: t[0], reverse=True)
        for _z, pts, fill in items:
            poly(pts, color=[0, 0, 0, 0], fill=fill, parent=dl)
    except Exception:
        return False
    return True


def _split_alpha(bt):
    t = max(0.0, min(1.0, float(bt)))
    return (max(0, min(255, int(round(255 * (1.0 - t))))),
            max(0, min(255, int(round(255 * t)))))


def _draw_morph_2d(dl, x, y, r, col, shp_a, shp_b, bt, glow_col):
    """Cross-fade companion shape; single draw outside the window."""
    if bt <= 0.0 or not shp_b or shp_b == shp_a:
        draw_shape_2d(dl, x, y, r, shp_a, col, glow_col)
        return
    aA, aB = _split_alpha(bt)
    draw_shape_2d(dl, x, y, r, shp_a,
                  [col[0], col[1], col[2], aA], None)
    draw_shape_2d(dl, x, y, r, shp_b,
                  [col[0], col[1], col[2], aB], None)


def _mesh_entry(fm, ref):
    """Assemble a draw-ready mesh tuple from frame_meshes() output.

    Falls back to the selected state's model (classic single-model
    behavior) and then to the sole entry, so particles outside the
    morph window — where no blend ref is known — still draw the mesh
    instead of the placeholder primitive.
    """
    if fm is None:
        return None
    entries, proj = fm
    e = entries.get(ref)
    if e is None:
        try:
            selref = state_model_ref(APP.states[APP.sel_state])
        except Exception:
            selref = ""
        e = entries.get(selref)
    if e is None and len(entries) == 1:
        e = next(iter(entries.values()))
    return (e[0], e[1], e[2], proj) if e else None


def _draw_side_3d(dl, mctx, shape, mesh_entry, col, sx, sy, r):
    """One morph side in 3D: mesh when resolved, else primitive."""
    if shape == "custom" and mesh_entry is not None and mctx is not None:
        wx, wy, wz, ws = mctx
        if draw_custom_mesh_3d(dl, mesh_entry, wx, wy, wz, ws, col):
            return
    draw_shape_3d(dl, sx, sy, r, shape, col)


def _draw_morph_3d(dl, mctx, sx, sy, r, col, side_a, side_b, bt, fm):
    """Cross-fade companion side; sides are (shape, ref) tuples."""
    shp_a, ref_a = side_a
    shp_b, ref_b = side_b
    same = (not shp_b or shp_b == shp_a) and not (
        shp_a == "custom" and ref_a != ref_b)
    if bt <= 0.0 or same:
        _draw_side_3d(dl, mctx, shp_a,
                      _mesh_entry(fm, ref_a) if shp_a == "custom" else None,
                      col, sx, sy, r)
        return
    aA, aB = _split_alpha(bt)
    _draw_side_3d(dl, mctx, shp_a,
                  _mesh_entry(fm, ref_a) if shp_a == "custom" else None,
                  [col[0], col[1], col[2], aA], sx, sy, r)
    _draw_side_3d(dl, mctx, shp_b,
                  _mesh_entry(fm, ref_b) if shp_b == "custom" else None,
                  [col[0], col[1], col[2], aB], sx, sy, r)


def dot_style(app, p):
    """(fill_rgba, radius, shape) shared by 2D/3D drawing."""
    if app.colormode == "gradient":
        smp = SimEngine.sample_tracks(p[13], p[4], p[20], p[21])
        return (_c(smp["color"]), max(1.5, smp["size"] * 0.45), smp["shape"])
    import re as _re
    st = app.states[app.sel_state] if 0 <= app.sel_state < len(app.states) else None
    col = ((st.get("appearance", {}) if st else {}).get("color") or "#ffffff")
    try:
        r0 = max(1.5, float(app.sf_size()) * 0.45)
    except (ValueError, TypeError):
        r0 = 4.0
    shp = (app.sf_shape() or "").lower()
    ok = PS.SHAPES_3D if app.ptype == "3d" else PS.SHAPES_2D
    if not _re.fullmatch(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", col or ""):
        col = "#ffffff"
    return (_c(col), r0, shp if shp in ok else ok[0])


def paint_bg_grid_2d(app, dl, W, H, cx, cy):
    """Viewport backdrop + perspective grid (no guides, no particles)."""
    dpg.draw_rectangle([0, 0], [W, H], color=[0, 0, 0, 0],
                       fill=[22, 23, 31, 255], parent=dl)
    gx, gy = cx + app.cam["ox"], cy + app.cam["oy"]
    ex, ey = gx + app.emitter2d[0], gy + app.emitter2d[1]
    horizon = H * 0.42 + app.cam["oy"]
    dpg.draw_line([0, horizon], [W, horizon], color=[58, 61, 85, 255], parent=dl)
    for i in range(1, 9):
        y = horizon + (H - horizon) * (i / 9) ** 1.6
        dpg.draw_line([0, y], [W, y], color=[44, 46, 68, 255], parent=dl)
    step = max(1, W / 14)
    for i in range(-10, 11):
        dpg.draw_line([gx, horizon], [gx + i * step, H],
                      color=[44, 46, 68, 255], parent=dl)
    return gx, horizon, ex, ey


def paint_guides_2d(app, dl, W, H, cx, cy, eff, gx, horizon, ex, ey):
    """Emission zone + propagation cone guides."""
    if eff is not None:
        em = eff["emitter"]
        if bool(em.get("emissionZone", {}).get("showZone", True)):
            z = em.get("emissionZone", {})
            zs = str(z.get("shape", "Circle")).lower()
            rot = math.radians(float(z.get("rotation", 0) or 0))
            cr, sr = math.cos(rot), math.sin(rot)
            blue = [77, 159, 255, 255]
            if zs == "rectangle":
                w = (z.get("width", 100) or 100) / 2
                h = (z.get("height", 60) or 60) / 2
                q = [(-w, -h), (w, -h), (w, h), (-w, h)]
                q = [[ex + x * cr - y * sr, ey + x * sr + y * cr] for x, y in q]
                dpg.draw_polygon(q, color=blue, parent=dl)
            elif zs == "line":
                ln = (z.get("length", 100) or 100) / 2
                a = [ex - ln * cr, ey - ln * sr]
                b = [ex + ln * cr, ey + ln * sr]
                dpg.draw_line(a, b, color=blue, parent=dl)
            elif zs != "point":
                r = max(4.0, float(z.get("radius", 10) or 10))
                dpg.draw_circle([ex, ey], r, color=blue, parent=dl, segments=40)
        cone = em.get("propagationCone", {})
        if bool(cone.get("showCone", True)):
            base = float(cone.get("direction", 0))
            spread = float(cone.get("spread", 90))
            if spread < 360:
                L = 110
                a1 = math.radians(base - spread / 2)
                a2 = math.radians(base + spread / 2)
                dpg.draw_line([ex, ey],
                              [ex + math.cos(a1) * L, ey + math.sin(a1) * L],
                              color=list(YELLOW) + [255], parent=dl)
                dpg.draw_line([ex, ey],
                              [ex + math.cos(a2) * L, ey + math.sin(a2) * L],
                              color=list(YELLOW) + [255], parent=dl)
                arc = [[ex + math.cos(math.radians(base - spread / 2 + spread * k / 16)) * L,
                        ey + math.sin(math.radians(base - spread / 2 + spread * k / 16)) * L]
                       for k in range(17)]
                dpg.draw_polyline(arc, color=list(YELLOW) + [255], parent=dl)
    return ex, ey


def paint_back_2d(app, dl, W, H, cx, cy, eff):
    """Viewport backdrop + grid + zone/cone guides (no particles)."""
    gx, horizon, ex, ey = paint_bg_grid_2d(app, dl, W, H, cx, cy)
    paint_guides_2d(app, dl, W, H, cx, cy, eff, gx, horizon, ex, ey)
    return ex, ey


def paint_dots_2d(app, dl, tracks):
    """Particle dots only (vector path)."""
    out = app.sim._cpp_out
    if out is not None:
        xs, ys, rs, cs, ss = out["x"], out["y"], out["r"], out["color"], out["shape"]
        n = len(xs)
        bseg_arr = out.get("bseg") if isinstance(out, dict) else None
        bt_arr = out.get("bt") if isinstance(out, dict) else None
        same_len = tracks is not None and len(tracks) == len(APP.states)
        glow = app.glow and n <= 450
        for i in range(n):
            col = _c("#%06x" % cs[i])
            if glow:
                hr = rs[i] * 2.2
                dpg.draw_circle([xs[i], ys[i]], hr,
                                color=[0, 0, 0, 0],
                                fill=[col[0] * 35 // 100, col[1] * 35 // 100,
                                      col[2] * 35 // 100, 255], parent=dl,
                                segments=16)
        for i in range(n):
            col_i = _c("#%06x" % cs[i])
            shp = PS.SHAPE_ORDER[ss[i]]
            shpA, shpB, bt = shp, None, 0.0
            if bseg_arr is not None and bt_arr is not None and same_len:
                try:
                    bs, t = int(bseg_arr[i]), float(bt_arr[i])
                except (ValueError, TypeError):
                    bs, t = -1, 0.0
                if 0 <= bs and bs + 1 < len(tracks) and 0.0 <= t <= 1.0:
                    shpA = tracks[bs]["shape"]
                    shpB = tracks[bs + 1]["shape"]
                    bt = t
            _draw_morph_2d(dl, xs[i], ys[i], rs[i], col_i,
                           shpA, shpB, bt, None)
    else:
        dots = []
        grad = (app.colormode == "gradient")
        for p in app.sim.parts:
            fill, r, shape = dot_style(app, p)
            shpA, shpB, bt = shape, None, 0.0
            if grad:
                try:
                    bs, t = SimEngine.blend_window(p[13], p[4])
                except Exception:
                    bs, t = -1, 0.0
                tr = p[13]
                if 0 <= bs and bs + 1 < len(tr) and 0.0 <= t <= 1.0:
                    shpA = tr[bs].get("shape", shape)
                    shpB = tr[bs + 1].get("shape", shape)
                    bt = t
            dots.append((p[0], p[1], r, shpA, shpB, bt, fill))
        glow = app.glow and len(dots) <= 450
        for x, y, r, a, b, bt, fill in dots:
            gc = None
            if glow:
                gc = [fill[0] * 35 // 100, fill[1] * 35 // 100,
                      fill[2] * 35 // 100, 255]
            _draw_morph_2d(dl, x, y, r, fill, a, b, bt, gc)


def paint_front_2d(dl, W, H, ex, ey):
    """Vignette + emitter gizmo overlay."""
    # vignette strips + gizmo
    m = min(W, H)
    t = max(14, m * 0.07)
    vc = [14, 16, 22, 255]
    dpg.draw_rectangle([0, 0], [W, t], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([0, H - t], [W, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([0, 0], [t, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([W - t, 0], [W, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_arrow([ex, ey], [ex + 95, ey], color=[255, 59, 59, 255],
                   thickness=6, parent=dl)
    dpg.draw_arrow([ex, ey], [ex, ey - 95], color=[47, 107, 255, 255],
                   thickness=6, parent=dl)
    dpg.draw_circle([ex, ey], 10, color=[123, 97, 255, 255],
                    fill=[255, 255, 255, 255], thickness=3, parent=dl,
                    segments=20)


def _smooth_pts(pts, subdiv):
    """Catmull-Rom subdivision (0 = off). Points are (x, y) or (x, y, z)."""
    if subdiv <= 0 or len(pts) < 4:
        return pts
    dim = len(pts[0])
    out = []
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        out.append(p1)
        for s in range(1, subdiv + 1):
            t = s / (subdiv + 1)
            t2, t3 = t * t, t * t * t
            q = []
            for c in range(dim):
                q.append(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t
                                + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3))
            out.append(tuple(q))
    out.append(pts[-1])
    return out


def paint_trails_2d(app, dl, eff):
    """One polyline per trail (vector overlay; ribbon strip lands in Part 4)."""
    try:
        tcfg = (eff.get("emitter") or {}).get("trails") if eff else None
    except Exception:
        return
    if not PS.trails_active(tcfg):
        return
    try:
        sub = max(0, int(tcfg.get("smoothing", 0) or 0))
        col = _c(str(tcfg.get("colorHead", "#ffffff") or "#ffffff"))
        a = max(0, min(255, int(tcfg.get("alphaHead", 255) or 0)))
        w = max(1, int(round(float(tcfg.get("widthStart", 8.0) or 0) * 0.5)))
        for hist in (getattr(app.sim, "trail_hist", {}) or {}).values():
            if len(hist) < 2:
                continue
            pts = _smooth_pts([(x, y) for (x, y, _z, _t) in hist], sub)
            dpg.draw_polyline(pts, color=[col[0], col[1], col[2], a],
                              thickness=w, parent=dl)
    except Exception:
        pass


def draw_view_2d(app, dl, W, H, cx, cy, eff, tracks=None):
    ex, ey = paint_back_2d(app, dl, W, H, cx, cy, eff)
    paint_dots_2d(app, dl, tracks)
    paint_trails_2d(app, dl, eff)
    paint_front_2d(dl, W, H, ex, ey)


def paint_bg_grid_3d(app, dl, W, H, cx, cy):
    """Viewport backdrop + perspective floor grid (no guides, no particles)."""
    dpg.draw_rectangle([0, 0], [W, H], color=[0, 0, 0, 0],
                       fill=[20, 21, 28, 255], parent=dl)
    app.cam["focal"] = ((max(100, H) * 0.5) /
                        max(0.05, math.tan(math.radians(app.fov / 2))))
    P = lambda x, y, z: app.proj(x, y, z, cx, cy)
    R, STEP = 260, 52
    for k in range(-R // STEP, R // STEP + 1):
        d = k * STEP
        x1, y1, _, _ = P(-R, 0, d)
        x2, y2, _, _ = P(R, 0, d)
        dpg.draw_line([x1, y1], [x2, y2], color=[44, 46, 68, 255], parent=dl)
        x1, y1, _, _ = P(d, 0, -R)
        x2, y2, _, _ = P(d, 0, R)
        dpg.draw_line([x1, y1], [x2, y2], color=[44, 46, 68, 255], parent=dl)


def paint_guides_3d(app, dl, cx, cy, em):
    """Emission zone + propagation cone guides."""
    P = lambda x, y, z: app.proj(x, y, z, cx, cy)
    zone = em.get("emissionZone", {})
    EX, EY, EZ = app.emitter_pos
    blue = [77, 159, 255, 255]
    if bool(zone.get("showZone", True)):
        zs = str(zone.get("shape", "sphere"))
        if zs == "sphere":
            r = max(4.0, float(zone.get("radius", 10) or 10))
            sx, sy, sc, _ = P(EX, EY, EZ)
            dpg.draw_circle([sx, sy], r * sc, color=blue, parent=dl, segments=40)
        elif zs == "box":
            w = float(zone.get("width", 100) or 100) / 2
            h = float(zone.get("height", 60) or 60) / 2
            d = float(zone.get("depth", 60) or 60) / 2
            rz = math.radians(float(zone.get("rotationZ", 0) or 0))
            crz, srz = math.cos(rz), math.sin(rz)
            v = [(-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
                 (-w, -h, d), (w, -h, d), (w, h, d), (-w, h, d)]
            v = [(EX + x * crz - y * srz, EY + x * srz + y * crz, EZ + z)
                 for (x, y, z) in v]
            q = [P(*p)[:2] for p in v]
            for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                         (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
                dpg.draw_line(list(q[a]), list(q[b]), color=blue, parent=dl)
        elif zs == "line":
            ln = (zone.get("length", 100) or 100) / 2
            rz = math.radians(float(zone.get("rotationZ", 0) or 0))
            crz, srz = math.cos(rz), math.sin(rz)
            a = P(EX - ln * crz, EY - ln * srz, EZ)[:2]
            b = P(EX + ln * crz, EY + ln * srz, EZ)[:2]
            dpg.draw_line(list(a), list(b), color=blue, parent=dl)
    cone = em.get("propagationCone", {})
    if bool(cone.get("showCone", True)):
        spread = float(cone.get("spread", 90))
        az = math.radians(float(cone.get("directionZ", 0)))
        el = math.radians(float(cone.get("directionY", 0)))
        if spread < 360:
            bx, by, bz = (math.cos(el) * math.cos(az), math.sin(el),
                          math.cos(el) * math.sin(az))
            ux, uy, uz = (0.0, 1.0, 0.0) if abs(by) < 0.95 else (1.0, 0.0, 0.0)
            ex_, ey_, ez_ = (by * uz - bz * uy, bz * ux - bx * uz,
                             bx * uy - by * ux)
            n = math.sqrt(ex_ ** 2 + ey_ ** 2 + ez_ ** 2) or 1.0
            ex_, ey_, ez_ = ex_ / n, ey_ / n, ez_ / n
            off = math.tan(math.radians(spread / 2))
            L = 110.0
            x1, y1, _, _ = P(EX, EY, EZ)
            for sgn in (1.0, -1.0):
                dx, dy, dz = (bx + ex_ * off * sgn, by + ey_ * off * sgn,
                              bz + ez_ * off * sgn)
                n2 = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                x2, y2, _, _ = P(EX + dx / n2 * L, EY + dy / n2 * L,
                                  EZ + dz / n2 * L)
                dpg.draw_line([x1, y1], [x2, y2],
                              color=list(YELLOW) + [255], parent=dl)


def paint_back_3d(app, dl, W, H, cx, cy, em):
    """Viewport backdrop + floor grid + zone/cone guides (no particles)."""
    paint_bg_grid_3d(app, dl, W, H, cx, cy)
    paint_guides_3d(app, dl, cx, cy, em)


def paint_dots_3d(app, dl, cx, cy, tracks):
    """Particle dots only (vector path, painter-sorted)."""
    P = lambda x, y, z: app.proj(x, y, z, cx, cy)
    out = app.sim._cpp_out
    focal = app.cam.get("focal", 620.0)
    if out is not None:
        order = sorted(range(len(out["x"])), key=out["depth"].__getitem__)
        fm, fm_done = None, False
        bseg_arr = out.get("bseg") if isinstance(out, dict) else None
        bt_arr = out.get("bt") if isinstance(out, dict) else None
        same_len = tracks is not None and len(tracks) == len(APP.states)
        for i in order:
            col = PS.StudioApp._depth_shade("#%06x" % out["color"][i],
                                            out["depth"][i], focal)
            sh = PS.SHAPE_ORDER[out["shape"][i]]
            colA = _c(col)
            shpA, shpB, refA, refB, bt = sh, None, "", "", 0.0
            if bseg_arr is not None and bt_arr is not None and same_len:
                try:
                    bs, t = int(bseg_arr[i]), float(bt_arr[i])
                except (ValueError, TypeError):
                    bs, t = -1, 0.0
                if 0 <= bs and bs + 1 < len(tracks) and 0.0 <= t <= 1.0:
                    shpA = tracks[bs]["shape"]
                    shpB = tracks[bs + 1]["shape"]
                    refA = state_model_ref(APP.states[bs])
                    refB = state_model_ref(APP.states[bs + 1])
                    bt = t
            mctx = None
            if (shpA == "custom" or shpB == "custom") and \
                    out["r"][i] >= MESH_MIN_R and \
                    len(out["x"]) <= MESH_MAX_PARTICLES:
                if not fm_done:
                    fm_done = True
                    fm = frame_meshes(app, cx, cy, len(out["x"]))
                if fm is not None:
                    _, _, sc0, _ = app.proj(out["wx"][i], out["wy"][i],
                                           out["z"][i], cx, cy)
                    if sc0 > 1e-6:
                        mctx = (out["wx"][i], out["wy"][i], out["z"][i],
                                out["r"][i] / sc0)
            _draw_morph_3d(dl, mctx, out["x"][i], out["y"][i], out["r"][i],
                           colA, (shpA, refA), (shpB, refB), bt, fm)
    else:
        projs = []
        for p in app.sim.parts:
            sx, sy, sc, depth = P(p[0], p[1], p[10])
            projs.append((depth, sx, sy, sc, p))
        projs.sort(key=lambda t: t[0])
        fm, fm_done = None, False
        grad = (app.colormode == "gradient")
        for depth, sx, sy, sc, p in projs:
            fill, r, shape = dot_style(app, p)
            shaded = PS.StudioApp._depth_shade(
                "#%02x%02x%02x" % tuple(fill[:3]), depth, focal)
            colA = _c(shaded)
            rs = max(1.0, r * sc)
            shpA, shpB, refA, refB, bt = shape, None, "", "", 0.0
            if grad:
                try:
                    bs, t = SimEngine.blend_window(p[13], p[4])
                except Exception:
                    bs, t = -1, 0.0
                tr = p[13]
                if 0 <= bs and bs + 1 < len(tr) and 0.0 <= t <= 1.0 \
                        and bs + 1 < len(APP.states):
                    shpA = tr[bs].get("shape", shape)
                    shpB = tr[bs + 1].get("shape", shape)
                    refA = state_model_ref(APP.states[bs])
                    refB = state_model_ref(APP.states[bs + 1])
                    bt = t
            mctx = None
            if (shpA == "custom" or shpB == "custom") and \
                    rs >= MESH_MIN_R and len(projs) <= MESH_MAX_PARTICLES:
                if not fm_done:
                    fm_done = True
                    fm = frame_meshes(app, cx, cy, len(projs))
                if fm is not None:
                    mctx = (p[0], p[1], p[10], r)
            _draw_morph_3d(dl, mctx, sx, sy, rs, colA,
                           (shpA, refA), (shpB, refB), bt, fm)


def paint_front_3d(app, dl, W, H, cx, cy):
    """Vignette + 3D emitter gizmo overlay."""
    P = lambda x, y, z: app.proj(x, y, z, cx, cy)
    EX, EY, EZ = app.emitter_pos
    m = min(W, H)
    t = max(14, m * 0.07)
    vc = [14, 16, 22, 255]
    dpg.draw_rectangle([0, 0], [W, t], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([0, H - t], [W, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([0, 0], [t, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    dpg.draw_rectangle([W - t, 0], [W, H], color=[0, 0, 0, 0], fill=vc, parent=dl)
    ox, oy, _, _ = P(EX, EY, EZ)
    for (ax, ay, az, col) in [(70, 0, 0, "#ff3b3b"), (0, 70, 0, "#3ddc84"),
                              (0, 0, 70, "#2f6bff")]:
        tx, ty, _, _ = P(EX + ax, EY + ay, EZ + az)
        dpg.draw_arrow([ox, oy], [tx, ty], color=_c(col), thickness=5,
                       parent=dl)
    dpg.draw_circle([ox, oy], 8, color=[0, 0, 0, 0], fill=[255, 255, 255, 255],
                    parent=dl, segments=16)


def paint_trails_3d(app, dl, cx, cy, eff):
    """One projected polyline per trail (vector overlay)."""
    try:
        tcfg = (eff.get("emitter") or {}).get("trails") if eff else None
    except Exception:
        return
    if not PS.trails_active(tcfg):
        return
    try:
        sub = max(0, int(tcfg.get("smoothing", 0) or 0))
        col = _c(str(tcfg.get("colorHead", "#ffffff") or "#ffffff"))
        a = max(0, min(255, int(tcfg.get("alphaHead", 255) or 0)))
        w = max(1, int(round(float(tcfg.get("widthStart", 8.0) or 0) * 0.5)))
        P = lambda x, y, z: app.proj(x, y, z, cx, cy)
        for hist in (getattr(app.sim, "trail_hist", {}) or {}).values():
            if len(hist) < 2:
                continue
            pts3 = _smooth_pts([(x, y, z) for (x, y, z, _t) in hist], sub)
            pts = []
            for (x, y, z) in pts3:
                sx, sy, _sc, _z = P(x, y, z)
                pts.append((sx, sy))
            dpg.draw_polyline(pts, color=[col[0], col[1], col[2], a],
                              thickness=w, parent=dl)
    except Exception:
        pass


def draw_view_3d(app, dl, W, H, cx, cy, em, tracks=None):
    paint_back_3d(app, dl, W, H, cx, cy, em)
    paint_dots_3d(app, dl, cx, cy, tracks)
    paint_trails_3d(app, dl, cx, cy, {"emitter": em} if em is not None else None)
    paint_front_3d(app, dl, W, H, cx, cy)


# ================= ImGui UI =================
def apply_theme():
    with dpg.theme() as th:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, list(BG) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, list(SIDEBAR) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, list(INPUT) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,
                                [52, 54, 70, 255])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,
                                [52, 54, 70, 255])
            dpg.add_theme_color(dpg.mvThemeCol_Button, list(CARD) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                [52, 54, 70, 255])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                list(ACCENT) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,
                                list(ACCENT) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,
                                list(ACCENT) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_Header, list(CARD) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,
                                [52, 54, 70, 255])
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,
                                [35, 36, 47, 255])
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,
                                [35, 36, 47, 255])
            dpg.add_theme_color(dpg.mvThemeCol_Text, list(TEXT) + [255])
            dpg.add_theme_color(dpg.mvThemeCol_Border, [53, 54, 70, 255])
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 6, 4)
    dpg.bind_theme(th)


ACCENT_THEME = None


def bind_accent_buttons():
    global ACCENT_THEME
    try:
        with dpg.theme() as accent_th:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                    list(ACCENT) + [255])
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                    [143, 118, 255, 255])
        ACCENT_THEME = accent_th
        dpg.bind_item_theme("export_btn", accent_th)
        dpg.bind_item_theme("preview_btn", accent_th)
    except Exception:
        pass


APP = App()
APP._f_was_down = False
APP._edge = {}
APP._drag_kind = None
APP.side_w = 320
APP._split = None
APP._split_hover = False


def show_msg(title, text):
    dpg.set_value("msg_text", text)
    dpg.configure_item("msg_win", label=title, show=True)


def em_set(path, value):
    """Write nested emitter dict: em_set(('gravity','x'), 1.0)."""
    d = APP.em
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = value
    APP.mark_dirty()


def cb_em_float(path):
    def _cb(sender=None, app_data=None, *r):
        try:
            em_set(path, float(app_data))
        except (ValueError, TypeError):
            pass
    return _cb


def cb_em_int(path):
    def _cb(sender=None, app_data=None, *r):
        try:
            em_set(path, int(app_data))
        except (ValueError, TypeError):
            pass
    return _cb


def cb_em_seed(sender=None, app_data=None, *r):
    """Seed box: store the value and reseed the spawn stream immediately."""
    try:
        em_set(("seed",), int(app_data))
        APP.sim.seed_sim(int(app_data))
    except (ValueError, TypeError):
        pass


def _field_col():
    f = APP.em.get("fields")
    if not isinstance(f, dict):
        f = {}
        APP.em["fields"] = f
    c = f.get("collision")
    if not isinstance(c, dict):
        c = {}
        f["collision"] = c
    return c


def cb_field_plane_toggle(sender=None, app_data=None, *r):
    """Plane checkbox: enable at 300 (or keep) / disable to null."""
    try:
        c = _field_col()
        if app_data:
            if c.get("planeY") is None:
                c["planeY"] = 300.0
                dpg.set_value("em_planey", 300.0)
        else:
            c["planeY"] = None
        APP.mark_dirty()
    except (ValueError, TypeError):
        pass


def cb_field_plane_y(sender=None, app_data=None, *r):
    """Plane Y value: setting a number implicitly enables the plane."""
    try:
        c = _field_col()
        c["planeY"] = float(app_data)
        dpg.set_value("em_plane_on", True)
        APP.mark_dirty()
    except (ValueError, TypeError):
        pass


def cb_em_combo(path, lower=False):
    def _cb(sender=None, app_data=None, *r):
        em_set(path, str(app_data).lower() if lower else str(app_data))
    return _cb


def cb_em_bool(path):
    def _cb(sender=None, app_data=None, *r):
        em_set(path, bool(app_data))
    return _cb


def cb_em_text(path):
    def _cb(sender=None, app_data=None, *r):
        em_set(path, str(app_data or ""))
    return _cb


def cur_state():
    if 0 <= APP.sel_state < len(APP.states):
        return APP.states[APP.sel_state]
    return None


def cb_st_text(key, conv=str):
    def _cb(sender=None, app_data=None, *r):
        if APP._restoring:
            return
        s = cur_state()
        if s is None:
            return
        try:
            s[key] = conv(app_data)
        except (ValueError, TypeError):
            return
        APP.mark_dirty()
    return _cb


def cb_st_ap(key, conv=float):
    def _cb(sender=None, app_data=None, *r):
        if APP._restoring:
            return
        s = cur_state()
        if s is None:
            return
        try:
            s.setdefault("appearance", {})[key] = conv(app_data)
        except (ValueError, TypeError):
            return
        APP.mark_dirty()
    return _cb


def cb_st_mv(key):
    def _cb(sender=None, app_data=None, *r):
        if APP._restoring:
            return
        s = cur_state()
        if s is None:
            return
        try:
            s.setdefault("movement", {})[key] = float(app_data)
        except (ValueError, TypeError):
            return
        APP.mark_dirty()
    return _cb


def cb_st_shape(sender=None, app_data=None, *r):
    if APP._restoring:
        return
    s = cur_state()
    if s is None:
        return
    s["shape"] = str(app_data)
    APP.mark_dirty()
    refresh_custom_row()


def cb_st_ease(sender=None, app_data=None, *r):
    if APP._restoring:
        return
    s = cur_state()
    if s is None:
        return
    s["easing"] = str(app_data)
    APP.mark_dirty()


@_safe_action
def cb_color_edit(sender=None, app_data=None, *r):
    if APP._restoring:
        return
    s = cur_state()
    if s is None:
        return
    vals = app_data
    if vals is None:
        # DPG sometimes invokes callbacks with no payload: fall back to
        # the widget's live value instead of dying silently (widget keeps
        # showing the picked color while the state never updates).
        try:
            vals = dpg.get_value(sender or "st_color_edit")
        except Exception:
            return
    try:
        comps = [float(vals[i]) for i in range(3)]
    except (ValueError, TypeError, IndexError):
        return
    # DPG may deliver 0-255 or normalized 0-1 floats; a fractional part
    # below 1.0 means normalized (whole numbers are the 0-255 scale).
    if all(0.0 <= v <= 1.0 for v in comps) and \
            any(v != 0.0 and v != 1.0 and v != float(int(v)) for v in comps):
        comps = [v * 255.0 for v in comps]
    r, g, b = [max(0, min(255, int(round(v)))) for v in comps]
    hx = "#%02x%02x%02x" % (r, g, b)
    s.setdefault("appearance", {})["color"] = hx
    s.setdefault("appearance", {})["opacity"] = 255
    try:
        dpg.set_value("st_color_hex", hx)
    except Exception:
        pass
    APP.mark_dirty()


@_safe_action
def cb_color_hex(sender=None, app_data=None, *r):
    if APP._restoring:
        return
    s = cur_state()
    if s is None:
        return
    hx = str(app_data).strip() if app_data is not None else ""
    if not hx:
        try:
            hx = str(dpg.get_value("st_color_hex")).strip()
        except Exception:
            return
    import re as _re
    if not _re.fullmatch(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", hx):
        # tolerate a missing leading '#'
        if _re.fullmatch(r"([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", hx):
            hx = "#" + hx
        else:
            return
    s.setdefault("appearance", {})["color"] = hx
    s.setdefault("appearance", {})["opacity"] = 255
    try:
        dpg.set_value("st_color_edit", tuple(hex_to_rgb(hx)) + (255,))
    except Exception:
        pass
    APP.mark_dirty()


def refresh_custom_row():
    try:
        s = cur_state()
        show = s is not None and str(s.get("shape", "")).lower() == "custom"
        dpg.configure_item("row_custom", show=show)
        dpg.configure_item("custom_hint", show=show)
        multi = show and APP.ptype == "3d" and len(APP._custom_nodes) > 1
        dpg.configure_item("row_custom_node", show=bool(multi))
        if show:
            dpg.set_value("upload_btn_label",
                          "Upload 3D" if APP.ptype == "3d" else "Upload image")
            cm = (s.get("customModel") or {}) if s else {}
            dpg.set_value("custom_file_text",
                          cm.get("file") or "no file")
    except Exception:
        pass


def rebuild_node_combo(nodes, keep=""):
    APP._custom_nodes = list(nodes)
    try:
        items = nodes if nodes else ["(whole file)"]
        dpg.configure_item("st_node", items=items)
        dpg.set_value("st_node", keep if keep in nodes else (nodes[0] if nodes else "(whole file)"))
    except Exception:
        pass


def refresh_chips():
    try:
        dpg.delete_item("chip_group", children_only=True)
        for i, s in enumerate(APP.states):
            sel = (i == APP.sel_state)
            dpg.add_button(label=("● " if sel else "○ ") + str(s.get("label")),
                           parent="chip_group",
                           callback=lambda *a, u=i: select_state(u))
    except Exception:
        pass


@_safe_action
def select_state(i):
    APP.sel_state = max(0, min(i, len(APP.states) - 1))
    APP.sync_state_form()
    refresh_chips()
    APP.mark_dirty()
    APP.history_commit()


def set_type(t, commit=True):
    APP.ptype = t
    APP.editor_mode = ("trail3d" if t == "3d" else "trail2d") \
        if getattr(APP, "trail", False) else t
    try:
        dpg.set_value("type_radio", "3D" if t == "3d" else "2D")
        zshapes = PS.ZONE_3D if t == "3d" else PS.ZONE_2D
        dpg.configure_item("em_zshape", items=zshapes)
        pshapes = PS.SHAPES_3D if t == "3d" else PS.SHAPES_2D
        dpg.configure_item("st_shape", items=pshapes)
        show3 = (t == "3d")
        dpg.configure_item("row_gz", show=show3)
        dpg.configure_item("row_diry", show=show3)
        dpg.configure_item("row_depth", show=show3)
        dpg.configure_item("row_zonemode", show=show3)
        dpg.set_value("dirz_label", "Dir. Z" if show3 else "Direction")
        z = APP.em.get("emissionZone", {})
        if t == "3d":
            z["shape"] = str(z.get("shape", "sphere")).lower()
            if z["shape"] not in PS.ZONE_3D:
                z["shape"] = "sphere"
            dpg.set_value("em_zshape", z["shape"])
        else:
            if z.get("shape") not in PS.ZONE_2D:
                z["shape"] = "Circle"
            dpg.set_value("em_zshape", z["shape"])
        s = cur_state()
        if s is not None and str(s.get("shape", "")).lower() not in pshapes:
            s["shape"] = pshapes[0]
        APP.sync_state_form()
        refresh_custom_row()
    except Exception:
        pass
    APP.sim.reset()
    APP.mark_dirty()
    if commit:
        APP.history_commit()


@_safe_action
def on_type_radio(sender=None, app_data=None, *r):
    try:
        v = app_data if app_data is not None else dpg.get_value("type_radio")
    except Exception:
        v = "2D"
    t = "3d" if str(v).upper() == "3D" else "2d"
    if t != APP.ptype:
        set_type(t)


# ================= widget sync =================
_orig_mark = App.mark_dirty


def _mark_dirty2(self):
    _orig_mark(self)
    self._need_commit = True


App.mark_dirty = _mark_dirty2
APP._need_commit = False


def _sf_size(self):
    s = cur_state()
    return float((s.get("appearance", {}) or {}).get("size", 8))


def _sf_shape(self):
    s = cur_state()
    return str((s or {}).get("shape", ""))


App.sf_size = _sf_size
App.sf_shape = _sf_shape


def _set(tag, value):
    try:
        dpg.set_value(tag, value)
    except Exception:
        pass


def sync_state_form(self):
    s = cur_state()
    if s is None:
        return
    ap = s.get("appearance", {})
    mv = s.get("movement", {})
    _set("st_label", str(s.get("label", "")))
    _set("st_dur", float(s.get("duration", 0.5) or 0.5))
    _set("st_shape", str(s.get("shape", "")))
    _set("st_ease", str(s.get("easing", "linear")))
    _set("st_size", float(ap.get("size", 8) or 0))
    _set("st_sizemax", float(ap.get("sizeMax", ap.get("size", 8)) or 0))
    # Show this state's own color (each state keeps its own appearance).
    hx = str(ap.get("color") or "#ffffff")
    import re as _re
    if not _re.fullmatch(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", hx):
        hx = "#ffffff"
    _set("st_color_hex", hx)
    try:
        dpg.set_value("st_color_edit", tuple(hex_to_rgb(hx)) + (255,))
    except Exception:
        pass
    _set("st_op", float(ap.get("opacity", 255)
                        if ap.get("opacity") is not None else 255))
    _set("st_mins", float(mv.get("minSpeed", 0) or 0))
    _set("st_maxs", float(mv.get("maxSpeed", mv.get("minSpeed", 0)) or 0))
    cm = s.get("customModel") or {}
    _set("custom_file_text", cm.get("file") or "no file")
    rebuild_node_combo(list(cm.get("nodes") or []), keep=cm.get("node", ""))
    refresh_custom_row()


App.sync_state_form = sync_state_form


def _sync_fields_form(f):
    """Push the fields block into the sidebar widgets (defaults when absent)."""
    d = PS.default_fields()
    if isinstance(f, dict):
        for k in ("turbulence", "vortex", "attractor", "collision"):
            if isinstance(f.get(k), dict):
                d[k].update(f[k])
    t, v, a, c = d["turbulence"], d["vortex"], d["attractor"], d["collision"]
    _set("em_turb", float(t.get("amount", 0) or 0))
    _set("em_turbsc", float(t.get("scale", 0.05) or 0))
    _set("em_turbsp", float(t.get("speed", 1.0) or 0))
    _set("em_vortex", float(v.get("strength", 0) or 0))
    _set("em_attr", float(a.get("strength", 0) or 0))
    _set("em_attrr", float(a.get("radius", 200) or 0))
    _set("em_attrx", float(a.get("x", 0) or 0))
    _set("em_attry", float(a.get("y", 0) or 0))
    py = c.get("planeY")
    try:
        py = float(py) if py is not None else None
    except (ValueError, TypeError):
        py = None
    _set("em_plane_on", py is not None)
    _set("em_planey", py if py is not None else 300.0)
    _set("em_bounce", float(c.get("bounce", 0.5) or 0))
    _set("em_fric", float(c.get("friction", 0.1) or 0))


def _sync_trails_form(t):
    """Push the trails block into the sidebar widgets (defaults when absent)."""
    d = PS.default_trails()
    if isinstance(t, dict):
        for k, v in t.items():
            if k in d:
                d[k] = v
    _set("em_trail_on", bool(d.get("enabled", False)))
    _set("em_trail_src", str(d.get("source", "particles") or "particles"))
    _set("em_trail_max", int(d.get("maxPoints", 32) or 32))
    _set("em_trail_life", float(d.get("lifetime", 1.0) or 0))
    _set("em_trail_mind", float(d.get("minDist", 4.0) or 0))
    _set("em_trail_mint", float(d.get("minTime", 0.016) or 0))
    _set("em_trail_smooth", int(d.get("smoothing", 0) or 0))
    _set("em_trail_w0", float(d.get("widthStart", 8.0) or 0))
    _set("em_trail_w1", float(d.get("widthEnd", 1.0) or 0))
    _set("em_trail_taper", float(d.get("taper", 1.0) or 0))
    _set("em_trail_uv", str(d.get("uvMode", "stretch") or "stretch"))
    _set("em_trail_tile", float(d.get("tileLength", 64.0) or 0))
    _set("em_trail_rib", str(d.get("ribbon", "billboard") or "billboard"))
    _set("em_trail_chead", str(d.get("colorHead", "#ffffff") or "#ffffff"))
    _set("em_trail_ctail", str(d.get("colorTail", "#ffffff") or "#ffffff"))
    _set("em_trail_ahead", int(d.get("alphaHead", 255) or 0))
    _set("em_trail_atail", int(d.get("alphaTail", 0) or 0))
    _set("em_trail_blend", str(d.get("blend", "inherit") or "inherit"))
    _set("em_trail_grav", float(d.get("gravity", 0.0) or 0))
    _set("em_trail_drag", float(d.get("drag", 0.0) or 0))
    _set("em_trail_noise", float(d.get("noise", 0.0) or 0))


def sync_emitter_form(self):
    e = self.em
    g = e.get("gravity", {})
    z = e.get("emissionZone", {})
    c = e.get("propagationCone", {})
    _set("em_flow", float(e.get("flow", 40)))
    _set("em_max", int(e.get("maxParticles", 300)))
    _set("em_mode", str(e.get("mode", "Infinite")))
    _set("em_rev", bool(e.get("reverse", False)))
    _set("em_align", bool(e.get("alignDir", False)))
    _set("em_blend", str(e.get("blendingMode", "Normal")))
    _set("em_seed", int(e.get("seed", 0) or 0))
    _sync_fields_form(e.get("fields"))
    _sync_trails_form(e.get("trails"))
    _set("em_gx", float(g.get("x", 0)))
    _set("em_gy", float(g.get("y", 0)))
    _set("em_gz", float(g.get("z", 0)))
    _set("em_zshape", str(z.get("shape", "Circle")))
    if self.ptype == "3d":
        _set("em_rot", float(z.get("rotationZ", z.get("rotation", 0)) or 0))
    else:
        _set("em_rot", float(z.get("rotation", 0) or 0))
    _set("em_radius", float(z.get("radius", 10) or 0))
    _set("em_width", float(z.get("width", 100) or 0))
    _set("em_height", float(z.get("height", 60) or 0))
    _set("em_length", float(z.get("length", 100) or 0))
    _set("em_depth", float(z.get("depth", 60) or 0))
    _set("em_zonemode", str(z.get("mode", "Surface")))
    _set("em_showzone", bool(z.get("showZone", True)))
    if self.ptype == "3d":
        _set("em_dirz", float(c.get("directionZ", c.get("direction", 0)) or 0))
    else:
        _set("em_dirz", float(c.get("direction", 0) or 0))
    _set("em_diry", float(c.get("directionY", 0) or 0))
    _set("em_spread", float(c.get("spread", 90) or 0))
    _set("em_showcone", bool(c.get("showCone", True)))


App.sync_emitter_form = sync_emitter_form


def sync_all(self):
    _set("filename_input", self.filename)
    _set("fov_input", float(self.fov))
    _set("sens_input", float(self.sens))
    _set("colormode_radio",
         "Selected" if self.colormode == "selected" else "Gradient")
    self.sync_emitter_form()
    self.sync_state_form()
    refresh_chips()


App.sync_all = sync_all


def cb_zone_rot(sender=None, app_data=None, *r):
    try:
        v = float(app_data)
    except (ValueError, TypeError):
        return
    z = APP.em.setdefault("emissionZone", {})
    if APP.ptype == "3d":
        z["rotationZ"] = v
    else:
        z["rotation"] = v
    APP.mark_dirty()


def cb_dirz(sender=None, app_data=None, *r):
    try:
        v = float(app_data)
    except (ValueError, TypeError):
        return
    c = APP.em.setdefault("propagationCone", {})
    if APP.ptype == "3d":
        c["directionZ"] = v
    else:
        c["direction"] = v
    APP.mark_dirty()


def cb_colormode(sender=None, app_data=None, *r):
    APP.colormode = "selected" if str(app_data) == "Selected" else "gradient"
    APP.mark_dirty()


def cb_st_node(sender=None, app_data=None, *r):
    if APP._restoring:
        return
    s = cur_state()
    if s is None:
        return
    v = str(app_data)
    if v == "(whole file)":
        v = ""
    cm = s.setdefault("customModel", {"file": "", "node": "", "kind": "model",
                                      "nodes": list(APP._custom_nodes)})
    cm["node"] = v
    _validate_custom_node(s)  # bone node -> whole file + warning
    APP.mark_dirty()


# ================= UI construction =================
def sec(title):
    dpg.add_text(title, color=list(MUTED) + [255])
    dpg.add_separator()


def num_row(label, tag, default, cb, width=-1):
    with dpg.group(horizontal=True):
        dpg.add_text(label, color=list(MUTED) + [255])
        dpg.add_input_float(tag=tag, default_value=float(default), width=width,
                            callback=cb)


def build_sidebar():
    sec("Emitter")
    dpg.add_text("PARTICLE OUTPUT", color=list(MUTED) + [255])
    num_row("Flow", "em_flow", 40, cb_em_float(("flow",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Max", color=list(MUTED) + [255])
        dpg.add_input_int(tag="em_max", default_value=300, width=-1,
                          callback=cb_em_int(("maxParticles",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Mode", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_mode", items=PS.MODES, default_value="Infinite",
                      width=-1, callback=cb_em_combo(("mode",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Reverse", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_rev", callback=cb_em_bool(("reverse",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Align dir.", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_align", default_value=True,
                         callback=cb_em_bool(("alignDir",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Blend", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_blend", items=PS.BLEND_MODES, default_value="Normal",
                      width=-1, callback=cb_em_combo(("blendingMode",)))
    with dpg.group(horizontal=True):
        dpg.add_text("Seed", color=list(MUTED) + [255])
        dpg.add_input_int(tag="em_seed", default_value=0, width=-1,
                          callback=cb_em_seed)
    dpg.add_text("FORCE FIELDS", color=list(MUTED) + [255])
    num_row("Turb amount", "em_turb", 0, cb_em_float(("fields", "turbulence", "amount")))
    num_row("Turb scale", "em_turbsc", 0.05, cb_em_float(("fields", "turbulence", "scale")))
    num_row("Turb speed", "em_turbsp", 1.0, cb_em_float(("fields", "turbulence", "speed")))
    num_row("Vortex", "em_vortex", 0, cb_em_float(("fields", "vortex", "strength")))
    num_row("Attr strength", "em_attr", 0, cb_em_float(("fields", "attractor", "strength")))
    num_row("Attr radius", "em_attrr", 200, cb_em_float(("fields", "attractor", "radius")))
    num_row("Attr X", "em_attrx", 0, cb_em_float(("fields", "attractor", "x")))
    num_row("Attr Y", "em_attry", 0, cb_em_float(("fields", "attractor", "y")))
    with dpg.group(horizontal=True):
        dpg.add_text("Plane", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_plane_on", callback=cb_field_plane_toggle)
    num_row("Plane Y", "em_planey", 300, cb_field_plane_y)
    num_row("Bounce", "em_bounce", 0.5, cb_em_float(("fields", "collision", "bounce")))
    num_row("Friction", "em_fric", 0.1, cb_em_float(("fields", "collision", "friction")))
    dpg.add_text("TRAIL SOURCE", color=list(MUTED) + [255])
    with dpg.group(horizontal=True):
        dpg.add_text("Enable", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_trail_on", callback=cb_em_bool(("trails", "enabled")))
    with dpg.group(horizontal=True):
        dpg.add_text("Source", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_trail_src", items=["particles", "emitter"],
                      default_value="particles", width=-1,
                      callback=cb_em_combo(("trails", "source")))
    num_row("Max points", "em_trail_max", 32, cb_em_int(("trails", "maxPoints")))
    num_row("Lifetime", "em_trail_life", 1.0, cb_em_float(("trails", "lifetime")))
    num_row("Min dist", "em_trail_mind", 4.0, cb_em_float(("trails", "minDist")))
    num_row("Min time", "em_trail_mint", 0.016, cb_em_float(("trails", "minTime")))
    num_row("Smoothing", "em_trail_smooth", 0, cb_em_int(("trails", "smoothing")))
    dpg.add_text("RIBBON GEOMETRY", color=list(MUTED) + [255])
    num_row("Width start", "em_trail_w0", 8.0, cb_em_float(("trails", "widthStart")))
    num_row("Width end", "em_trail_w1", 1.0, cb_em_float(("trails", "widthEnd")))
    num_row("Taper", "em_trail_taper", 1.0, cb_em_float(("trails", "taper")))
    with dpg.group(horizontal=True):
        dpg.add_text("UV mode", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_trail_uv", items=["stretch", "tile"],
                      default_value="stretch", width=-1,
                      callback=cb_em_combo(("trails", "uvMode")))
    num_row("Tile length", "em_trail_tile", 64.0, cb_em_float(("trails", "tileLength")))
    with dpg.group(horizontal=True):
        dpg.add_text("Ribbon", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_trail_rib", items=["billboard", "fixed", "flat"],
                      default_value="billboard", width=-1,
                      callback=cb_em_combo(("trails", "ribbon")))
    dpg.add_text("TRAIL COLOR", color=list(MUTED) + [255])
    with dpg.group(horizontal=True):
        dpg.add_text("Head", color=list(MUTED) + [255])
        dpg.add_input_text(tag="em_trail_chead", default_value="#ffffff",
                           width=-1, callback=cb_em_text(("trails", "colorHead")))
    with dpg.group(horizontal=True):
        dpg.add_text("Tail", color=list(MUTED) + [255])
        dpg.add_input_text(tag="em_trail_ctail", default_value="#ffffff",
                           width=-1, callback=cb_em_text(("trails", "colorTail")))
    num_row("Alpha head", "em_trail_ahead", 255, cb_em_int(("trails", "alphaHead")))
    num_row("Alpha tail", "em_trail_atail", 0, cb_em_int(("trails", "alphaTail")))
    with dpg.group(horizontal=True):
        dpg.add_text("Blend", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_trail_blend",
                      items=["inherit"] + list(PS.BLEND_MODES),
                      default_value="inherit", width=-1,
                      callback=cb_em_combo(("trails", "blend")))
    dpg.add_text("TRAIL MOTION", color=list(MUTED) + [255])
    num_row("Gravity", "em_trail_grav", 0.0, cb_em_float(("trails", "gravity")))
    num_row("Drag", "em_trail_drag", 0.0, cb_em_float(("trails", "drag")))
    num_row("Noise", "em_trail_noise", 0.0, cb_em_float(("trails", "noise")))
    dpg.add_text("GRAVITY", color=list(MUTED) + [255])
    num_row("Gravity X", "em_gx", 0, cb_em_float(("gravity", "x")))
    num_row("Gravity Y", "em_gy", 0, cb_em_float(("gravity", "y")))
    with dpg.group(horizontal=True, tag="row_gz", show=False):
        dpg.add_text("Gravity Z", color=list(MUTED) + [255])
        dpg.add_input_float(tag="em_gz", default_value=0, width=-1,
                            callback=cb_em_float(("gravity", "z")))
    dpg.add_text("EMISSION ZONE", color=list(MUTED) + [255])
    with dpg.group(horizontal=True):
        dpg.add_text("Shape", color=list(MUTED) + [255])
        dpg.add_combo(tag="em_zshape", items=PS.ZONE_2D, default_value="Circle",
                      width=-1, callback=cb_em_combo(("emissionZone", "shape")))
    num_row("Rotation", "em_rot", 0, cb_zone_rot)
    num_row("Radius", "em_radius", 10, cb_em_float(("emissionZone", "radius")))
    num_row("Width", "em_width", 100, cb_em_float(("emissionZone", "width")))
    num_row("Height", "em_height", 60, cb_em_float(("emissionZone", "height")))
    num_row("Length", "em_length", 100, cb_em_float(("emissionZone", "length")))
    with dpg.group(horizontal=True, tag="row_depth", show=False):
        dpg.add_text("Depth", color=list(MUTED) + [255])
        dpg.add_input_float(tag="em_depth", default_value=60, width=-1,
                            callback=cb_em_float(("emissionZone", "depth")))
    with dpg.group(horizontal=True, tag="row_zonemode", show=False):
        dpg.add_text("Mode", color=list(MUTED) + [255])
        dpg.add_radio_button(tag="em_zonemode", items=PS.ZONE_MODE,
                             default_value="Surface", horizontal=True,
                             callback=cb_em_combo(("emissionZone", "mode")))
    with dpg.group(horizontal=True):
        dpg.add_text("Show zone", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_showzone", default_value=True,
                         callback=cb_em_bool(("emissionZone", "showZone")))
    dpg.add_text("PROPAGATION CONE", color=list(MUTED) + [255])
    with dpg.group(horizontal=True):
        dpg.add_text("Direction", color=list(MUTED) + [255], tag="dirz_label")
        dpg.add_input_float(tag="em_dirz", default_value=0, width=-1,
                            callback=cb_dirz)
    with dpg.group(horizontal=True, tag="row_diry", show=False):
        dpg.add_text("Dir. Y", color=list(MUTED) + [255])
        dpg.add_input_float(tag="em_diry", default_value=0, width=-1,
                            callback=cb_em_float(("propagationCone",
                                                  "directionY")))
    num_row("Spread", "em_spread", 90,
            cb_em_float(("propagationCone", "spread")))
    with dpg.group(horizontal=True):
        dpg.add_text("Show cone", color=list(MUTED) + [255])
        dpg.add_checkbox(tag="em_showcone", default_value=True,
                         callback=cb_em_bool(("propagationCone", "showCone")))
    sec("States")
    with dpg.group(horizontal=True):
        dpg.add_text("Preview", color=list(MUTED) + [255])
        dpg.add_radio_button(tag="colormode_radio",
                             items=["Selected", "Gradient"],
                             default_value="Gradient", horizontal=True,
                             callback=cb_colormode)
    with dpg.group(horizontal=True):
        dpg.add_text("Label", color=list(MUTED) + [255])
        dpg.add_input_text(tag="st_label", default_value="birth", width=-1,
                           callback=cb_st_text("label"))
    with dpg.group(horizontal=True):
        dpg.add_text("Duration", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_dur", default_value=0.5, width=-1,
                            callback=cb_st_text("duration", float))
    with dpg.group(horizontal=True):
        dpg.add_text("Shape", color=list(MUTED) + [255])
        dpg.add_combo(tag="st_shape", items=PS.SHAPES_2D,
                      default_value="circle", width=-1, callback=cb_st_shape)
    with dpg.group(horizontal=True):
        dpg.add_text("Easing", color=list(MUTED) + [255])
        dpg.add_combo(tag="st_ease", items=PS.EASINGS,
                      default_value="linear", width=-1, callback=cb_st_ease)
    with dpg.group(horizontal=True):
        dpg.add_text("Size", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_size", default_value=8, width=-1,
                            callback=cb_st_ap("size"))
    with dpg.group(horizontal=True):
        dpg.add_text("SizeMax", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_sizemax", default_value=12, width=-1,
                            callback=cb_st_ap("sizeMax"))
    with dpg.group(horizontal=True):
        dpg.add_text("Color", color=list(MUTED) + [255])
        dpg.add_color_edit(tag="st_color_edit",
                           default_value=(255, 255, 255, 255), width=-1,
                           callback=cb_color_edit)
        dpg.add_input_text(tag="st_color_hex", default_value="#ffffff",
                           width=90, callback=cb_color_hex)
    with dpg.group(horizontal=True):
        dpg.add_text("Opacity", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_op", default_value=255, width=-1,
                            callback=cb_st_ap("opacity",
                                              lambda v: int(float(v))))
    with dpg.group(horizontal=True):
        dpg.add_text("MinSpeed", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_mins", default_value=60, width=-1,
                            callback=cb_st_mv("minSpeed"))
    with dpg.group(horizontal=True):
        dpg.add_text("MaxSpd", color=list(MUTED) + [255])
        dpg.add_input_float(tag="st_maxs", default_value=160, width=-1,
                            callback=cb_st_mv("maxSpeed"))
    with dpg.group(horizontal=True):
        dpg.add_button(label="Save", callback=lambda *a: save_state(),
                       width=90)
        dpg.add_button(label="Delete", callback=lambda *a: del_state(),
                       width=90)
    with dpg.group(horizontal=True, tag="row_custom", show=False):
        dpg.add_button(label="Upload 3D", tag="upload_btn_label",
                       callback=lambda *a: upload_custom_model(), width=110)
        dpg.add_text("no file", tag="custom_file_text",
                     color=list(MUTED) + [255])
        dpg.add_button(label="X", callback=lambda *a: clear_custom_model(),
                       width=30)
    with dpg.group(horizontal=True, tag="row_custom_node", show=False):
        dpg.add_text("Node", color=list(MUTED) + [255])
        dpg.add_combo(tag="st_node", items=["(whole file)"],
                      default_value="(whole file)", width=-1,
                      callback=cb_st_node)
    dpg.add_text("", tag="custom_hint", show=False, wrap=260)
    sec("Templates")
    with dpg.group(horizontal=True):
        for name in PS.TEMPLATES:
            dpg.add_button(label=name, width=74,
                           callback=lambda *a, u=name: apply_template(u))
    dpg.add_button(label="Export JSON", tag="export_btn", width=-1, height=36,
                   callback=lambda *a: do_save_as())


def build_topbar():
    with dpg.group(horizontal=True):
        dpg.add_text("Carrot Studio", color=[255, 122, 0, 255])
        dpg.add_input_text(tag="filename_input", default_value="Default",
                           width=130,
                           callback=lambda s, a, *r: setattr(APP, "filename",
                                                         str(a) or "Default"))
        dpg.add_radio_button(tag="type_radio", items=["2D", "3D"],
                             default_value="2D", horizontal=True,
                             callback=on_type_radio)
        dpg.add_text("FOV", color=list(MUTED) + [255])
        dpg.add_input_float(tag="fov_input", default_value=60.0, width=60,
                            callback=lambda s, a, *r: (
                                setattr(APP, "fov",
                                        max(10.0, min(120.0, float(a)))),
                                APP.mark_dirty()))
        dpg.add_text("Sens", color=list(MUTED) + [255])
        dpg.add_input_float(tag="sens_input", default_value=1.0, width=60,
                            callback=lambda s, a, *r: setattr(
                                APP, "sens",
                                max(0.1, min(5.0, float(a)))))
        dpg.add_button(label="New", callback=lambda *a: do_new(), width=60)
        dpg.add_button(label="Save", callback=lambda *a: do_save(), width=60)
        dpg.add_button(label="Save As", callback=lambda *a: do_save_as(),
                       width=80)
        dpg.add_button(label="Open", callback=lambda *a: do_open(), width=60)


def build_timeline():
    with dpg.group(horizontal=True):
        dpg.add_text("STATES", color=list(MUTED) + [255])
        dpg.add_group(tag="chip_group", horizontal=True)
        dpg.add_button(label="+", callback=lambda *a: add_state(), width=36)
        dpg.add_button(label="Fast preview 60FPS", tag="preview_btn",
                       callback=lambda *a: open_fast_preview())
        dpg.add_text("Ready", tag="status_text", color=list(OK) + [255])


def build_viewport():
    with dpg.child_window(tag="vp_child", autosize_x=True, height=-1,
                          border=False):
        dpg.add_drawlist(tag="vp_draw", width=800, height=536)
        build_timeline()


def load_fonts():
    """Segoe UI (like the old Tk edition) instead of the built-in
    monospace-looking font. Falls back to default when missing."""
    try:
        candidates = [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\WinNT\Fonts\segoeui.ttf",
        ]
        path = next((p for p in candidates if os.path.isfile(p)), None)
        if path is None:
            return
        with dpg.font_registry():
            dpg.add_font(path, 17, tag="font_ui")
            dpg.add_font(path, 15, tag="font_sm")
        dpg.bind_font("font_ui")
    except Exception as e:
        PS.debug_log("font-fallback", repr(e)[:200])


# ================= chooser modes (data-driven) =================
# id: editor mode; ptype: sim dimensionality ("2d"/"3d");
# trail: Trails/Ribbons overlay flag; key: keyboard shortcut.
MODES = [
    {"id": "2d", "label": "2D  |  Sprites & SVG", "key": "2",
     "ptype": "2d", "trail": False},
    {"id": "3d", "label": "3D  |  Meshes & Billboards", "key": "3",
     "ptype": "3d", "trail": False},
    {"id": "trail2d", "label": "2D  |  Trails & Ribbons", "key": "4",
     "ptype": "2d", "trail": True},
    {"id": "trail3d", "label": "3D  |  Trails & Ribbons", "key": "5",
     "ptype": "3d", "trail": True},
]
MODE_BY_ID = {m["id"]: m for m in MODES}
MODE_BY_KEY = {m["key"]: m for m in MODES}
CHOOSER_BTN_W, CHOOSER_BTN_H = 220, 84


def build_chooser():
    with dpg.window(tag="chooser_win", label="Carrot Particle Editor",
                    modal=True, show=True, no_resize=True, no_move=True,
                    width=480, height=600, pos=[400, 100]):
        try:
            w, h, ch, data = dpg.load_image(
                os.path.join(PS.app_base_dir(), "assets", "app_icon.png"))
            with dpg.texture_registry():
                dpg.add_static_texture(w, h, data, tag="logo_tex")
            dpg.add_spacer(height=6)
            dpg.add_image("logo_tex", width=200, height=200, pos=[140, 40])
            dpg.add_spacer(height=206)
        except Exception:
            pass
        dpg.add_text("CARROT", color=[255, 122, 0, 255])
        dpg.add_text("PARTICLE EDITOR", color=[0, 200, 83, 255])
        dpg.add_text("ParticleFX — Choose your editor mode",
                     color=list(MUTED) + [255])
        dpg.add_separator()
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            for m in MODES[:2]:
                dpg.add_button(label=m["label"], width=CHOOSER_BTN_W,
                               height=CHOOSER_BTN_H,
                               callback=lambda *a, _id=m["id"]: choose(_id))
        with dpg.group(horizontal=True):
            for m in MODES[2:4]:
                dpg.add_button(label=m["label"], width=CHOOSER_BTN_W,
                               height=CHOOSER_BTN_H,
                               callback=lambda *a, _id=m["id"]: choose(_id))
        dpg.add_spacer(height=6)
        dpg.add_text("press 2 / 3 / 4 / 5", color=list(MUTED) + [255])


def _dialog_cancelled(sender=None, app_data=None, *r):
    """Fires only when a file dialog is dismissed via Cancel.

    Lets empty main-callback fires be told apart from real cancellations
    in the debug log (a Cancel must never look like a failed OK).
    """
    try:
        PS.debug_log("DLG-CANCEL", str(sender))
    except Exception:
        pass


def build_dialogs():
    with dpg.file_dialog(tag="dlg_open", show=False, width=600, height=400,
                         callback=open_chosen,
                         cancel_callback=_dialog_cancelled):
        dpg.add_file_extension(".json")
    with dpg.file_dialog(tag="dlg_save", show=False, width=600, height=400,
                         callback=save_chosen,
                         cancel_callback=_dialog_cancelled):
        dpg.add_file_extension(".json")
    with dpg.window(tag="msg_win", label="Message", modal=True, show=False,
                    width=420, height=160, pos=[430, 320]):
        dpg.add_text("", tag="msg_text", wrap=380)
        dpg.add_button(label="OK", width=80,
                       callback=lambda *a: dpg.configure_item("msg_win",
                                                           show=False))


def build_ui():
    with dpg.window(tag="primary"):
        build_topbar()
        dpg.add_separator()
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="side_child", width=APP.side_w,
                                  height=-1):
                build_sidebar()
            build_viewport()
    dpg.set_primary_window("primary", True)
    build_chooser()
    build_dialogs()
    with dpg.handler_registry():
        dpg.add_mouse_wheel_handler(
            callback=lambda s, a, *r: setattr(APP, "_wheel",
                                          APP._wheel + float(a)))
        dpg.add_mouse_double_click_handler(
            button=dpg.mvMouseButton_Left,
            callback=lambda *a: setattr(APP, "_dblclick", True))
        for key, name in ((dpg.mvKey_Z, "z"), (dpg.mvKey_Y, "y"),
                          (dpg.mvKey_S, "s"), (dpg.mvKey_2, "2"),
                          (dpg.mvKey_3, "3"), (dpg.mvKey_4, "4"),
                          (dpg.mvKey_5, "5")):
            dpg.add_key_press_handler(
                key=key,
                callback=lambda *a, u=name: APP._keys.append(u))
        for _nk, _nm in (("Numpad2", "2"), ("Numpad3", "3"),
                         ("Numpad4", "4"), ("Numpad5", "5")):
            _kc = getattr(dpg, "mvKey_" + _nk, None)
            if _kc is not None:
                dpg.add_key_press_handler(
                    key=_kc,
                    callback=lambda *a, u=_nm: APP._keys.append(u))
    APP._keys = []
    bind_accent_buttons()


# ================= actions =================



@_safe_action
def choose(mode_id):
    m = MODE_BY_ID.get(mode_id, MODE_BY_ID["2d"])
    ptype, trail = m["ptype"], m["trail"]
    PS.debug_log("CHOOSE", m["id"])
    dpg.configure_item("chooser_win", show=False)
    APP._editor_open = True
    APP.trail = trail
    APP.editor_mode = m["id"]
    set_type(ptype, commit=False)
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()
    if trail:
        APP.set_status("Trails & Ribbons mode (" + ptype.upper() + ")",
                       MUTED)


@_safe_action
def add_state():
    s = cur_state()
    APP.states.append(PS.default_state("intermediate", len(APP.states)))
    APP.sel_state = len(APP.states) - 1
    APP.sync_state_form()
    refresh_chips()
    APP.mark_dirty()
    APP.history_commit()


@_safe_action
def del_state():
    if len(APP.states) <= 2:
        show_msg("Notice", "birth + death required")
        return
    APP.states.pop(APP.sel_state)
    APP.sel_state = 0
    APP.sync_state_form()
    refresh_chips()
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()


@_safe_action
def save_state():
    APP.sync_state_form()
    refresh_chips()
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()


@_safe_action
def apply_template(name):
    tpl = PS.TEMPLATES[name]
    patch = tpl[APP.ptype]
    em = PS.default_emitter(APP.ptype)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(em.get(k), dict):
            em[k].update(v)
        else:
            em[k] = v
    APP.em = em
    states_key = "states2d" if APP.ptype == "2d" else "states3d"
    if tpl.get(states_key):
        APP.states = copy.deepcopy(tpl[states_key])
        APP.sel_state = 0
    APP.sync_all()
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()


@_safe_action
def do_new():
    APP.filepath = None
    APP.filename = "Default"
    APP.em = PS.default_emitter(APP.ptype)
    APP.states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
    APP.sel_state = 0
    APP.sync_all()
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()


def _apply_loaded_effect(eff, path):
    try:
        eff, _warns = PS.migrate_effect(eff)
    except ValueError as e:
        show_msg("Error", str(e))
        return
    APP.filepath = path
    APP.filename = os.path.splitext(os.path.basename(path))[0]
    APP.ptype = eff.get("type", "2d")
    if APP.ptype not in ("2d", "3d"):
        APP.ptype = "2d"
    set_type(APP.ptype, commit=False)
    APP.states = eff.get("states", APP.states)
    APP.sel_state = 0
    APP.em = eff.get("emitter", PS.default_emitter("2d"))
    APP.sync_all()
    APP.sim.reset()
    APP.sim.seed_sim((eff.get("emitter") or {}).get("seed", 0))
    APP.mark_dirty()
    APP.history_commit()
    if _warns:
        APP.set_status("Migrated: " + " | ".join(_warns)[:200], WARN)


def dialog_pick(app_data):
    """Extract a picked file path from a DPG file-dialog payload.

    Key names vary across DPG versions and selections may arrive as a
    dict or a list, so accept every known shape. Returns "" when nothing
    usable was delivered (e.g. the dialog was cancelled).
    """
    try:
        if not isinstance(app_data, dict):
            return ""
        sels = app_data.get("selections") or {}
        if isinstance(sels, dict):
            for v in sels.values():
                if v:
                    return str(v)
        elif isinstance(sels, (list, tuple)):
            for v in sels:
                if v:
                    return str(v)
        for k in ("file_path_name", "file_path", "path", "file"):
            v = app_data.get(k)
            if v:
                return str(v)
        fn = app_data.get("file_name") or app_data.get("filename")
        cp = app_data.get("current_path") or app_data.get("current_dir")
        if fn and cp:
            return os.path.join(str(cp), str(fn))
        return ""
    except Exception:
        return ""


def do_open():
    p, err = _native_effect_path("open")
    if err:
        show_msg("Error", err)
        return
    if not p:
        return  # user cancelled the OS picker
    try:
        _load_path(p)
    except Exception as e:
        show_msg("Error", str(e))


def _load_path(p):
    """Open + migrate + apply an effect file. Raises on failure."""
    with open(p, encoding="utf-8") as f:
        eff = json.load(f)
    _apply_loaded_effect(eff, p)


@_safe_action
def open_chosen(sender=None, app_data=None, *r):
    try:
        PS.debug_log("DLG-OPEN",
                     str(sorted((app_data or {}).keys()))[:200])
        p = dialog_pick(app_data)
        if not p:
            return
        _load_path(p)
    except Exception as e:
        show_msg("Error", str(e))


def gather():
    APP.filename = (dpg.get_value("filename_input") or "").strip() or "Default"
    eff = APP.current_effect()
    errs = PS.validate_effect(eff)
    APP.set_status("OK — ready" if not errs else " | ".join(errs),
                   OK if not errs else WARN)
    return eff


@_safe_action
def do_save():
    if not APP.filepath:
        do_save_as()
        return
    eff = gather()
    try:
        with open(APP.filepath, "w", encoding="utf-8") as f:
            json.dump(eff, f, indent=2, ensure_ascii=False)
        APP.set_status("Saved", OK)
    except OSError as e:
        show_msg("Error", str(e))


@_safe_action
def do_save_as():
    p, err = _native_effect_path("save")
    if err:
        show_msg("Error", err)
        return
    if not p:
        return  # user cancelled the OS picker
    try:
        p = _write_path(p)
    except Exception as e:
        show_msg("Error", str(e))
        return
    show_msg("Done", f"Exported:\n{p}\n\nAdd it in GDevelop as a JSON "
                     "resource into ParticleJSON.")


def _write_path(p):
    """Validate + write the effect JSON. Raises on failure. Shared by the
    OS picker and the legacy DPG dialog fallback."""
    if not p.lower().endswith(".json"):
        p += ".json"
    eff = gather()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(eff, f, indent=2, ensure_ascii=False)
    APP.filepath = p
    return p


@_safe_action
def save_chosen(sender=None, app_data=None, *r):
    try:
        PS.debug_log("DLG-SAVE",
                     str(sorted((app_data or {}).keys()))[:200])
        p = dialog_pick(app_data)
        if not p:
            return
        p = _write_path(p)
        show_msg("Done", f"Exported:\n{p}\n\nAdd it in GDevelop as a JSON "
                         "resource into ParticleJSON.")
    except Exception as e:
        show_msg("Error", str(e))


@_safe_action
def upload_custom_model():
    kind = "model" if APP.ptype == "3d" else "image"
    path, err = _native_pick(kind)
    if err:
        show_msg("Error", err)
        return
    if not path:
        return  # user cancelled the OS picker
    _custom_chosen(path, kind)


def _native_pick(kind):
    """OS-native file picker (tkinter): returns (path, error).
    Synchronous plain path string — no DPG payload quirks. ("", "") means
    the user cancelled; ("", message) means the picker itself failed.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        if kind == "model":
            title = "Pick 3D model"
            fts = [("3D models", "*.glb *.gltf *.obj"), ("All files", "*.*")]
        else:
            title = "Pick image"
            fts = [("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.svg"),
                   ("All files", "*.*")]
        root = tk.Tk()
        try:
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            path = filedialog.askopenfilename(title=title, filetypes=fts)
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        return (path or "", "")
    except Exception as e:
        PS.debug_log("NATIVE-DLG-EXC", str(e)[:200])
        return ("", f"Could not open file picker:\n{e}")


def _native_effect_path(mode):
    """OS-native open/save dialog for effect JSON files.

    The Dear PyGui file dialog delivers empty payloads on this setup
    (see DLG-SAVE [] in the debug log), so Save/Export/Open bypass it
    exactly like model/image picking already does. Returns (path, error);
    ("", "") means the user cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        start = os.path.dirname(APP.filepath) \
            if getattr(APP, "filepath", None) else os.getcwd()
        root = tk.Tk()
        try:
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            if mode == "save":
                initial = (getattr(APP, "filename", "") or "Default").strip() \
                    or "Default"
                path = filedialog.asksaveasfilename(
                    title="Export effect JSON",
                    defaultextension=".json",
                    filetypes=[("JSON", "*.json"), ("All files", "*.*")],
                    initialdir=start, initialfile=f"{initial}.json")
            else:
                path = filedialog.askopenfilename(
                    title="Open effect JSON",
                    filetypes=[("JSON", "*.json"), ("All files", "*.*")],
                    initialdir=start)
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        return (path or "", "")
    except Exception as e:
        PS.debug_log("NATIVE-EFFECT-EXC", str(e)[:200])
        return ("", f"Could not open file picker:\n{e}")


def _validate_custom_node(s):
    """Fall back to whole file when the picked node holds no mesh.

    Bone-only nodes (robot Head/foot.R) resolve to zero triangles, which
    renders as the placeholder forever. Returns True when the selection
    is usable; otherwise clears the node (+stale ref) and warns.
    """
    try:
        cm = s.get("customModel") or {}
        node = str(cm.get("node") or "")
        if not node:
            return True
        path = cm.get("path") or ""
        if not path or not os.path.isfile(path):
            path = _find_model_file(cm.get("file") or "")
        if not path:
            return True
        tris, _, _ = mesh_cache.load_mesh(path, node)
        if tris:
            return True
        cm["node"] = ""
        fname = cm.get("file") or ""
        stem = os.path.splitext(fname)[0] if fname else ""
        if stem and (s.get("modelRefs") or [""])[0] not in ("", stem):
            s["modelRefs"] = [stem]
        rebuild_node_combo(list(cm.get("nodes") or []), keep="")
        refresh_custom_row()
        APP.set_status(f"Node '{node}' has no mesh — whole file shown",
                       WARN)
        APP.mark_dirty()
        return False
    except Exception:
        return True


def _custom_chosen(path, kind):
    if not path:
        return
    fname = os.path.basename(path)
    nodes = PS.model_nodes_from_file(path) if kind == "model" else []
    s = cur_state()
    if s is None:
        return
    node = dpg.get_value("st_node") if kind == "model" else ""
    if node == "(whole file)":
        node = ""
    s["customModel"] = {"file": fname, "path": path, "node": node,
                        "kind": kind, "nodes": list(nodes)}
    if fname:
        ref = node or os.path.splitext(fname)[0]
        if kind == "model":
            s["modelRefs"] = [ref]
        else:
            s["customShapeRefs"] = [fname]
    APP.sync_state_form()
    APP.sim.reset()
    APP.mark_dirty()
    APP.history_commit()
    extra = f" ({len(nodes)} nodes)" if kind == "model" else ""
    APP.set_status(f"Model loaded: {fname}{extra}", OK)
    if kind == "model":
        _validate_custom_node(s)  # stale/bone node -> whole file + warning


@_safe_action
def clear_custom_model():
    s = cur_state()
    if s is None:
        return
    s.pop("customModel", None)
    s.pop("modelRefs", None)
    APP.sync_state_form()
    APP.mark_dirty()
    APP.history_commit()


# ================= fast browser preview (reuses PS server) =================
_preview_server = None
_preview_port = 0


@_safe_action
def open_fast_preview():
    global _preview_server, _preview_port
    eff = gather()
    blobs = PS.model_blobs_for_states(APP.states)
    if blobs:
        eff["modelsData"] = blobs
    base = PS.app_base_dir()
    pv_dir = os.path.join(base, "preview")
    try:
        os.makedirs(pv_dir, exist_ok=True)
        with open(os.path.join(pv_dir, "last_effect.json"), "w",
                  encoding="utf-8") as f:
            json.dump(eff, f, ensure_ascii=False)
    except OSError as e:
        show_msg("Error", f"Cannot write preview file:\n{e}")
        return
    if _preview_server is None:
        handler = partial(PS._QuietHTTPHandler, directory=base)
        try:
            srv = PS._PreviewHTTPServer(("127.0.0.1", 0), handler)
        except OSError as e:
            show_msg("Error", f"Cannot start preview server: {e}")
            return
        _preview_port = srv.server_address[1]
        _preview_server = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{_preview_port}/preview/preview.html"
    try:
        with open(os.path.join(pv_dir, "preview.html"), encoding="utf-8") as f:
            tpl = f.read()
        with open(os.path.join(pv_dir, "live_bundle.js"), encoding="utf-8") as f:
            bundle = f.read()
        boot = json.dumps(eff, ensure_ascii=False).replace("</", "<\\/")
        page = tpl.replace('<script type="module" src="./main.js"></script>',
                           "<script type=\"module\">\n" + bundle +
                           "\n</script>", 1)
        page = page.replace('<script id="boot-effect" type="application/json">'
                            "</script>",
                            '<script id="boot-effect" type="application/json">'
                            + boot + "</script>", 1)
        if page == tpl or "__previewBooted" not in page:
            raise ValueError("template markers missing")
        with open(os.path.join(pv_dir, "live_effect.html"), "w",
                  encoding="utf-8") as f:
            f.write(page)
        url = f"http://127.0.0.1:{_preview_port}/preview/live_effect.html"
    except Exception:
        pass
    try:
        import urllib.request as _url
        opener = _url.build_opener(_url.ProxyHandler({}))
        with opener.open(url, timeout=5) as _r:
            if getattr(_r, "status", 200) != 200:
                raise OSError(f"HTTP {getattr(_r, 'status', '?')}")
    except Exception as e:
        show_msg("Error", f"Preview server not responding:\n{e}")
        return
    APP._live_push_on = True
    webbrowser.open(url)


# ================= mouse + frame loop =================
def gizmo_hit(lx, ly, W, H, cx, cy):
    if APP.ptype == "3d":
        o = APP.proj(*APP.emitter_pos, cx, cy)[:2]
        if math.hypot(lx - o[0], ly - o[1]) <= 24:
            return "move"
        for i, (ax, ay, az) in enumerate(((70, 0, 0), (0, 70, 0),
                                          (0, 0, 70))):
            ex, ey, ez = APP.emitter_pos
            t = APP.proj(ex + ax, ey + ay, ez + az, cx, cy)[:2]
            dx, dy = t[0] - o[0], t[1] - o[1]
            n = math.hypot(dx, dy)
            if n < 1e-6:
                continue
            along = ((lx - o[0]) * dx + (ly - o[1]) * dy) / n
            perp = abs((lx - o[0]) * dy - (ly - o[1]) * dx) / n
            if 0 <= along <= n and perp <= 16:
                return ("axis", i)
        return None
    ex = cx + APP.cam["ox"] + APP.emitter2d[0]
    ey = cy + APP.cam["oy"] + APP.emitter2d[1]
    if math.hypot(lx - ex, ly - ey) <= 24:
        return "move2d"
    return None


def _typing():
    """True while typing in a text/numeric/combo field (navigation keys
    must not hijack typing)."""
    try:
        f = dpg.get_focused_item()
        if not f:
            return False
        t = dpg.get_item_type(f)
        return t in ("mvAppItemType::mvInputText",
                     "mvAppItemType::mvInputFloat",
                     "mvAppItemType::mvInputInt",
                     "mvAppItemType::mvCombo",
                     "mvAppItemType::mvColorEdit")
    except Exception:
        return False


def focus_emitter(W, H, cx, cy):
    """Frame the emitter at the viewport center (F key)."""
    if APP.ptype == "3d":
        sx, sy = APP.proj(*APP.emitter_pos, cx, cy)[:2]
    else:
        sx = cx + APP.cam["ox"] + APP.emitter2d[0]
        sy = cy + APP.cam["oy"] + APP.emitter2d[1]
    APP.cam["ox"] += cx - sx
    APP.cam["oy"] += cy - sy
    APP.mark_dirty()
    APP.history_commit()


def _space_down():
    try:
        return bool(dpg.is_key_down(dpg.mvKey_Space))
    except Exception:
        return False


def _edge(name, down):
    was = APP._edge.get(name, False)
    APP._edge[name] = down
    return down and not was


def _npkey(n):
    return getattr(dpg, f"mvKey_Numpad{n}", None)


def handle_nav_keys(dt, W, H, cx, cy):
    """Game-engine style navigation, every frame.

    3D (Blender-like): A/D orbit yaw, W/S dolly, Q/E move up-down,
    arrows pan, MMB orbit, Shift+MMB pan, wheel dolly, 1/3/7 views,
    F focus emitter, Home reset view, Shift x3.
    2D (GDevelop-like): WASD/arrows pan, Q/E zoom, wheel zooms at the
    cursor, Space+left-drag pan, F focus, Home reset, Shift x3.
    Skipped while typing or before the editor opens."""
    if not APP._editor_open:
        return
    try:
        if dpg.is_item_shown("chooser_win"):
            return
    except Exception:
        pass
    if _typing():
        return
    sens = APP.sens * (3.0 if _shift_down() else 1.0)
    is3d = APP.ptype == "3d"
    if is3d:
        yaw_in = int(dpg.is_key_down(dpg.mvKey_D)) - \
            int(dpg.is_key_down(dpg.mvKey_A))
        if yaw_in:
            APP.cam["yaw"] += yaw_in * 1.8 * sens * dt
            APP.mark_dirty()
        fw = int(dpg.is_key_down(dpg.mvKey_W)) - \
            int(dpg.is_key_down(dpg.mvKey_S))
        if fw:
            k = math.exp(1.1 * sens * dt)
            APP.cam["zoom"] = max(0.3, min(4.0, APP.cam["zoom"] *
                                           (k if fw > 0 else 1 / k)))
            APP.mark_dirty()
        vert = int(dpg.is_key_down(dpg.mvKey_E)) - \
            int(dpg.is_key_down(dpg.mvKey_Q))
        dx = int(dpg.is_key_down(dpg.mvKey_Right)) - \
            int(dpg.is_key_down(dpg.mvKey_Left))
        dy = int(dpg.is_key_down(dpg.mvKey_Down)) - \
            int(dpg.is_key_down(dpg.mvKey_Up))
        if dx or dy or vert:
            v = 340 * sens * dt
            APP.cam["ox"] += dx * v
            APP.cam["oy"] += (dy + vert) * v
            APP.mark_dirty()
        views = []
        for n, yaw, pitch in ((1, 0.0, 0.0), (3, math.pi / 2, 0.0),
                              (7, 0.0, 1.55)):
            key = _npkey(n)
            if key is not None:
                try:
                    views.append((n, yaw, pitch,
                                  dpg.is_key_down(key)))
                except Exception:
                    pass
        for n, yaw, pitch, down in views:
            if _edge(f"np{n}", down):
                APP.cam["yaw"] = yaw
                APP.cam["pitch"] = pitch
                APP.mark_dirty()
    else:
        dx = int(dpg.is_key_down(dpg.mvKey_D)) - \
            int(dpg.is_key_down(dpg.mvKey_A)) + \
            int(dpg.is_key_down(dpg.mvKey_Right)) - \
            int(dpg.is_key_down(dpg.mvKey_Left))
        dy = int(dpg.is_key_down(dpg.mvKey_S)) - \
            int(dpg.is_key_down(dpg.mvKey_W)) + \
            int(dpg.is_key_down(dpg.mvKey_Down)) - \
            int(dpg.is_key_down(dpg.mvKey_Up))
        if dx or dy:
            v = 340 * sens * dt
            APP.cam["ox"] += dx * v
            APP.cam["oy"] += dy * v
            APP.mark_dirty()
        zin = dpg.is_key_down(dpg.mvKey_E)
        zout = dpg.is_key_down(dpg.mvKey_Q)
        if zin or zout:
            k = math.exp(0.9 * sens * dt)
            APP.cam["zoom"] = max(0.3, min(4.0, APP.cam["zoom"] *
                                           (k if zin else 1 / k)))
            APP.mark_dirty()
    f_down = dpg.is_key_down(dpg.mvKey_F)
    if f_down and not APP._f_was_down:
        focus_emitter(W, H, cx, cy)
    APP._f_was_down = f_down
    try:
        home_down = dpg.is_key_down(dpg.mvKey_Home)
    except Exception:
        home_down = False
    if _edge("home", bool(home_down)):
        APP.cam.update({"yaw": 0.7, "pitch": 0.42, "zoom": 1.0,
                        "ox": 0.0, "oy": 0.0})
        APP.mark_dirty()
        APP.history_commit()


def sidebar_hovered():
    """True when the mouse is over anything in the left panel (rect math,
    independent of the stale drawing-space mouse position)."""
    try:
        mp = dpg.get_mouse_pos()
        smin = dpg.get_item_rect_min("side_child")
        smax = dpg.get_item_rect_max("side_child")
        return (smin[0] <= mp[0] < smax[0] and
                smin[1] <= mp[1] < smax[1])
    except Exception:
        return False


def handle_splitter(lx, hover):
    # While dragging, anchor in SCREEN x (valid inside and outside the
    # viewport). Drawing-space lx freezes once the cursor leaves vp_draw,
    # which made shrinking stall after the panel grew.
    if APP._split is not None:
        if dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
            try:
                mx = float(dpg.get_mouse_pos()[0])
            except Exception:
                return True
            ax, aw = APP._split
            APP.side_w = max(200, min(520, aw + (mx - ax)))
            try:
                dpg.configure_item("side_child", width=int(APP.side_w))
            except Exception:
                pass
            return True
        APP._split = None
        return False
    if hover and 0 <= lx <= 6 and \
            dpg.is_mouse_button_clicked(dpg.mvMouseButton_Left):
        try:
            mx = float(dpg.get_mouse_pos()[0])
        except Exception:
            mx = lx
        APP._split = (mx, APP.side_w)
        return True
    APP._split_hover = bool(hover and 0 <= lx <= 6)
    return False


def handle_mouse(lx, ly, hover, W, H, cx, cy, zoom_ok=True):
    if APP._dblclick:
        APP._dblclick = False
        if hover and gizmo_hit(lx, ly, W, H, cx, cy) is None:
            APP.cam.update({"yaw": 0.7, "pitch": 0.42, "zoom": 1.0,
                            "ox": 0.0, "oy": 0.0})
            APP.emitter_pos = [0.0, 0.0, 0.0]
            APP.emitter2d = [0.0, 0.0]
            APP.history_commit()
    if APP._wheel and hover and zoom_ok:
        if APP.ptype == "3d":
            # pure dolly in place (anchoring would swing the orbit target)
            k = (1.12 ** APP.sens) ** APP._wheel
            APP.cam["zoom"] = max(0.3, min(4.0, APP.cam["zoom"] * k))
        else:
            # zoom anchored at the cursor (world point under mouse stays)
            k = (1.12 ** APP.sens) ** APP._wheel
            old = APP.cam["zoom"]
            new = max(0.3, min(4.0, old * k))
            s = new / old if old > 1e-9 else 1.0
            APP.cam["ox"] = lx - cx - (lx - cx - APP.cam["ox"]) * s
            APP.cam["oy"] = ly - cy - (ly - cy - APP.cam["oy"]) * s
            APP.cam["zoom"] = new
        APP.mark_dirty()
    APP._wheel = 0
    if not hover:
        return
    if dpg.is_mouse_button_clicked(dpg.mvMouseButton_Left):
        if _space_down():
            # Space+drag pans (GDevelop/Unity style), gizmo stays put
            APP._drag = (lx, ly)
            APP._drag_kind = "pan"
            APP._gizmo = None
        else:
            hit = gizmo_hit(lx, ly, W, H, cx, cy)
            if os.environ.get("CARROT_DEBUG_MOUSE"):
                try:
                    _mx2, _my2 = dpg.get_mouse_pos(local=False)
                except Exception:
                    _mx2, _my2 = (-1, -1)
                PS.debug_log("MOUSE-CLICK",
                             f"lx={lx:.1f} ly={ly:.1f} W={W} H={H} "
                             f"cx={cx:.0f} cy={cy:.0f} hit={hit} "
                             f"mxy={mx:.1f},{my:.1f} mglob={_mx2:.1f},{_my2:.1f} "
                             f"rmin={rmin}")
            APP._gizmo = None if hit is None else {"kind": hit,
                                                   "x": lx, "y": ly}
    if dpg.is_mouse_button_released(dpg.mvMouseButton_Left):
        if APP._gizmo is not None:
            APP._gizmo = None
            APP.history_commit()
        if APP._drag_kind == "pan":
            APP._drag = None
            APP._drag_kind = None
            APP.history_commit()
    if dpg.is_mouse_button_released(dpg.mvMouseButton_Right) or \
       dpg.is_mouse_button_released(dpg.mvMouseButton_Middle):
        if APP._drag is not None:
            APP._drag = None
            APP._drag_kind = None
            APP.history_commit()
    if dpg.is_mouse_button_clicked(dpg.mvMouseButton_Right):
        APP._drag = (lx, ly)
        APP._drag_kind = "orbit"
    if dpg.is_mouse_button_clicked(dpg.mvMouseButton_Middle):
        APP._drag = (lx, ly)
        APP._drag_kind = "pan"
    g = APP._gizmo
    if g is not None and dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
        dx, dy = lx - g["x"], ly - g["y"]
        g["x"], g["y"] = lx, ly
        if g["kind"] == "move2d":
            APP.emitter2d[0] += dx
            APP.emitter2d[1] += dy
        elif APP.ptype == "3d":
            syaw, cyaw = math.sin(APP.cam["yaw"]), math.cos(APP.cam["yaw"])
            spit, cpit = math.sin(APP.cam["pitch"]), math.cos(APP.cam["pitch"])
            right = (cyaw, 0.0, syaw)
            up = (spit * syaw, cpit, -spit * cyaw)
            sc = max(1e-6, APP.proj(*APP.emitter_pos, cx, cy)[2])
            if g["kind"] == "move":
                APP.emitter_pos[0] += (dx * right[0] - dy * up[0]) / sc
                APP.emitter_pos[1] += (dx * right[1] - dy * up[1]) / sc
                APP.emitter_pos[2] += (dx * right[2] - dy * up[2]) / sc
            else:
                i = g["kind"][1]
                o = APP.proj(*APP.emitter_pos, cx, cy)[:2]
                ex, ey, ez = APP.emitter_pos
                off = ((70, 0, 0), (0, 70, 0), (0, 0, 70))[i]
                t = APP.proj(ex + off[0], ey + off[1], ez + off[2], cx, cy)[:2]
                ax, ay = t[0] - o[0], t[1] - o[1]
                n = math.hypot(ax, ay)
                if n >= 1e-6:
                    along = (dx * ax + dy * ay) / n / sc
                    unit = ((1, 0, 0), (0, 1, 0), (0, 0, 1))[i]
                    APP.emitter_pos[0] += unit[0] * along
                    APP.emitter_pos[1] += unit[1] * along
                    APP.emitter_pos[2] += unit[2] * along
    if APP._drag is not None:
        kind = APP._drag_kind
        if kind == "orbit" and \
                dpg.is_mouse_button_down(dpg.mvMouseButton_Right):
            # Blender-style orbit (3D) with the right button
            if APP.ptype == "3d":
                dx, dy = lx - APP._drag[0], ly - APP._drag[1]
                APP._drag = (lx, ly)
                APP.cam["yaw"] += dx * 0.01 * APP.sens
                APP.cam["pitch"] = max(-1.4, min(1.4, APP.cam["pitch"] +
                                                 dy * 0.01 * APP.sens))
        elif kind == "pan" and \
                (dpg.is_mouse_button_down(dpg.mvMouseButton_Middle) or
                 (dpg.is_mouse_button_down(dpg.mvMouseButton_Left) and
                  _space_down())):
            # middle-drag, or Space+left-drag (GDevelop/Unity style)
            dx, dy = lx - APP._drag[0], ly - APP._drag[1]
            APP._drag = (lx, ly)
            APP.cam["ox"] += dx * APP.sens
            APP.cam["oy"] += dy * APP.sens


def _ctrl_down():
    return dpg.is_key_down(dpg.mvKey_LControl) or \
        dpg.is_key_down(dpg.mvKey_RControl)


def _shift_down():
    return dpg.is_key_down(dpg.mvKey_LShift) or \
        dpg.is_key_down(dpg.mvKey_RShift)


def handle_keys():
    keys = list(APP._keys)
    APP._keys.clear()
    ctrl = _ctrl_down()
    for k in keys:
        if k == "z" and ctrl:
            APP.undo() if not _shift_down() else APP.redo()
        elif k == "y" and ctrl:
            APP.redo()
        elif k == "s" and ctrl:
            do_save()
        elif k in ("2", "3", "4", "5") and dpg.is_item_shown("chooser_win"):
            choose(MODE_BY_KEY[k]["id"])


def frame():
    t0 = time.time()
    try:
        dt = min(0.05, max(1e-3, t0 - APP.sim.last_t))
        APP.sim.last_t = t0
        eff = APP.cached_effect()
        try:
            cw, ch = (int(v) for v in dpg.get_item_rect_size("vp_child"))
        except Exception:
            cw, ch = (900, 640)
        W, H = max(100, cw), max(100, ch - 70)
        try:
            dpg.configure_item("vp_draw", width=W, height=H)
        except Exception:
            pass
        cx, cy = W * 0.5, H * 0.52
        if eff is not None and APP.ptype == "2d":
            scx = cx + APP.cam["ox"] + APP.emitter2d[0]
            scy = cy + APP.cam["oy"] + APP.emitter2d[1]
        else:
            scx, scy = cx, cy
        cpp_n, cpp_active = 0, False
        tracks = None
        if eff is not None:
            em = eff["emitter"]
            # NOTE: correct axis mapping (Tk edition had gx/gy swapped).
            gx = em.get("gravity", {}).get("x", 0) * dt * 0.4
            gy = em.get("gravity", {}).get("y", 0) * dt * 0.4
            gz = em.get("gravity", {}).get("z", 0) * dt * 0.4
            maxp = min(SimEngine.TK_MAX_DOTS,
                       int(em.get("maxParticles", 300) or 300))
            if HAS_CPP_CORE:
                try:
                    is3d = APP.ptype == "3d"
                    if is3d:
                        APP.cam["focal"] = ((max(100, H) * 0.5) /
                                            max(0.05, math.tan(math.radians(
                                                APP.fov / 2))))
                    tracks = SimEngine._build_tracks(APP.states, APP.ptype)
                    cpp_n = APP.sim.step_cpp(
                        eff, em, APP.ptype, tracks, is3d, dt, scx, scy,
                        tuple(APP.emitter_pos), APP.cam,
                        APP.cam.get("focal", 620.0), cx, cy,
                        gx, gy, gz, maxp, (APP.ptype, APP._cache_t))
                    cpp_active = True
                except Exception:
                    APP.sim._cpp_eng = None
                    APP.sim._cpp_key = None
                    APP.sim._cpp_out = None
            if not cpp_active:
                APP.sim._cpp_out = None
                tracks = SimEngine._build_tracks(APP.states, APP.ptype)
                cpp_n = APP.sim.step_py(em, APP.ptype, scx, scy,
                                        tuple(APP.emitter_pos), APP.cam,
                                        tracks, dt, maxp)
        else:
            APP.sim._cpp_out = None
        handle_keys()
        try:
            hov = bool(dpg.is_item_hovered("vp_draw"))
        except Exception:
            hov = False
        try:
            lx, ly = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            lx, ly = (0, 0)
        in_d = 0 <= lx < W and 0 <= ly < H
        try:
            mx2, my2 = dpg.get_mouse_pos()
            rmin2 = dpg.get_item_rect_min("vp_draw")
            lx_r, ly_r = mx2 - rmin2[0], my2 - rmin2[1]
        except Exception:
            lx_r, ly_r = (0, 0)
        in_r = 0 <= lx_r < W and 0 <= ly_r < H
        if in_d and (hov or not in_r):
            hover = True
        elif in_r:
            lx, ly, hover = lx_r, ly_r, True
        else:
            hover = False
        _side = sidebar_hovered()
        if _side:
            # wheel over the panel scrolls the panel, never zooms viewport
            hover = False
            APP._wheel = 0
        # zoom gate: cursor must be inside the viewport rect AND outside
        # the panel, even if the fuzzy hover flag got polluted
        zoom_ok = bool(hover) and bool(in_r) and not _side
        if os.environ.get("CARROT_DEBUG_MOUSE") and \
                not getattr(APP, "_geo_logged", False) and \
                time.time() - getattr(APP, "_t_start", time.time()) > 5:
            APP._geo_logged = True
            try:
                import ctypes as _ct
                _hwnd = _ct.windll.user32.GetForegroundWindow()
                _r = (_ct.c_long * 4)()
                _ct.windll.user32.GetWindowRect(_hwnd, _r)
                _wrect = tuple(_r)
            except Exception:
                _wrect = ("?",)
            try:
                _vp = dpg.get_viewport_pos()
            except Exception:
                _vp = ("?",)
            try:
                _m1 = dpg.get_mouse_pos()
            except Exception:
                _m1 = ("?",)
            try:
                _m2 = dpg.get_mouse_pos(local=False)
            except Exception:
                _m2 = ("?",)
            try:
                _rmn = dpg.get_item_rect_min("vp_draw")
                _rmx = dpg.get_item_rect_max("vp_draw")
            except Exception as _e:
                _rmn, _rmx = (f"ERR:{type(_e).__name__}", None)
            try:
                _parts = []
                for _tag in ("vp_draw", "vp_child", "side_child",
                             "primary"):
                    try:
                        _mn = dpg.get_item_rect_min(_tag)
                        _mx = dpg.get_item_rect_max(_tag)
                    except Exception as _e:
                        _mn, _mx = (f"ERR:{type(_e).__name__}", None)
                    _parts.append(f"{_tag}={_mn}/{_mx}")
                try:
                    _pos = dpg.get_item_pos("vp_draw")
                except Exception as _e:
                    _pos = f"ERR:{type(_e).__name__}"
                _parts.append(f"pos={_pos}")
            except Exception:
                _parts = ["?"]
            PS.debug_log("GEO2", " ".join(str(p) for p in _parts))
        split_busy = False
        try:
            split_busy = handle_splitter(lx, hover)
        except Exception:
            PS.debug_log("IMG-SPLIT-EXC",
                         traceback.format_exc().replace("\n", " | ")[:500])
        if not split_busy:
            handle_mouse(lx, ly, hover, W, H, cx, cy, zoom_ok)
        try:
            handle_nav_keys(dt, W, H, cx, cy)
        except Exception:
            PS.debug_log("IMG-NAV-EXC",
                         traceback.format_exc().replace("\n", " | ")[:500])
        try:
            dpg.delete_item("vp_draw", children_only=True)
            is3d = (eff is not None and APP.ptype == "3d" and "directionZ" in
                    eff.get("emitter", {}).get("propagationCone", {}))
            n_show = cpp_n if cpp_active else len(APP.sim.parts)
            _fr, _tag = None, ""
            if RV is not None and RV.should_raster(APP, n_show):
                try:
                    if is3d:
                        _fr = RV.frame_3d(APP, APP.sim._cpp_out, W, H, cx, cy)
                    else:
                        _fr = RV.frame_2d(APP, APP.sim._cpp_out, W, H)
                except Exception:
                    _fr = None
                if _fr is not None:
                    _tag = RV.ensure_texture(_fr[0], _fr[1])
                    if not (_tag and RV.update_texture(_fr[2])):
                        _fr = None
            APP._raster_on = _fr is not None
            if _fr is not None:
                # raster particle layer (bg+grid+dots via GL), then vector
                # guides/front on top. bg+grid draw first (cheap) so the
                # guide painters can reuse their geometry math, then the
                # image covers them.
                if is3d:
                    paint_bg_grid_3d(APP, "vp_draw", W, H, cx, cy)
                else:
                    _gx, _hz, _ex, _ey = paint_bg_grid_2d(
                        APP, "vp_draw", W, H, cx, cy)
                dpg.draw_image(_tag, [0, 0], [W, H], parent="vp_draw")
                if is3d:
                    paint_guides_3d(APP, "vp_draw", cx, cy, eff["emitter"])
                    paint_trails_3d(APP, "vp_draw", cx, cy, eff)
                    paint_front_3d(APP, "vp_draw", W, H, cx, cy)
                else:
                    paint_guides_2d(APP, "vp_draw", W, H, cx, cy, eff,
                                    _gx, _hz, _ex, _ey)
                    paint_trails_2d(APP, "vp_draw", eff)
                    paint_front_2d("vp_draw", W, H, _ex, _ey)
            elif is3d:
                draw_view_3d(APP, "vp_draw", W, H, cx, cy, eff["emitter"],
                             tracks)
            else:
                draw_view_2d(APP, "vp_draw", W, H, cx, cy, eff, tracks)
            if APP._split is not None or APP._split_hover:
                dpg.draw_line([2, 0], [2, H], color=[123, 97, 255, 255],
                              thickness=3, parent="vp_draw")
            if os.environ.get("CARROT_DEBUG_MOUSE"):
                try:
                    dpg.draw_circle([lx, ly], 12, color=[0, 255, 0, 255],
                                    thickness=2, parent="vp_draw",
                                    segments=16)
                    dpg.draw_text([lx + 16, ly - 8],
                                  f"{int(lx)},{int(ly)}",
                                  color=[0, 255, 0, 255], size=16,
                                  parent="vp_draw")
                    dpg.draw_circle([lx_r, ly_r], 12, color=[255, 0, 0, 255],
                                    thickness=2, parent="vp_draw",
                                    segments=16)
                except Exception:
                    pass
            n_show = cpp_n if cpp_active else len(APP.sim.parts)
            APP._n_show = n_show
            APP._cpp_active = cpp_active
            fps = int(1 / max(time.time() - t0, 1e-3))
            APP._fps = min(fps, 240)
            tag = "C++" if cpp_active else "PY"
            dpg.draw_text([W - 220, 12],
                          f"Particles: {n_show}  FPS: {APP._fps} {tag}",
                          color=[232, 232, 238, 255], size=15,
                          parent="vp_draw")
            hint = ("3D Blender-style: A/D orbit, W/S dolly, Q/E up-down, "
                    "MMB orbit, wheel dolly, 1/3/7 views, F focus" if
                    APP.ptype == "3d" else
                    "2D GDevelop-style: WASD/arrows move, wheel zoom at "
                    "cursor, Space+drag pan, F focus | left-drag gizmo")
            dpg.draw_text([max(8, W / 2 - 280), H - 24], hint,
                          color=[154, 154, 173, 255], size=14,
                          parent="vp_draw")
        except Exception:
            PS.debug_log("IMG-TICK-EXC",
                         traceback.format_exc().replace("\n", " | ")[:1000])
        now = time.time()
        if getattr(APP, "_need_commit", False) and \
                now - APP._last_edit > 0.8 and not APP._restoring:
            APP._need_commit = False
            APP.history_commit()
        if APP._live_push_on and now - APP._last_push > 0.5:
            APP._last_push = now
            try:
                ce = APP.current_effect()
                fp = PS.model_fingerprint(APP.states)
                if fp != APP._models_fp:
                    APP._models_fp = fp
                    ce["modelsData"] = PS.model_blobs_for_states(APP.states)
                with open(os.path.join(PS.app_base_dir(), "preview",
                                       "last_effect.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(ce, f, ensure_ascii=False)
            except Exception:
                pass
        auto = os.environ.get("CARROT_AUTO")
        if auto in MODE_BY_ID and dpg.is_item_shown("chooser_win"):
            choose(auto)
    except Exception:
        PS.debug_log("IMG-FRAME-EXC",
                     traceback.format_exc().replace("\n", " | ")[:1000])


def main():
    PS.debug_log("boot-imgui", BUILD_ID)
    dpg.create_context()
    dpg.create_viewport(title=f"Carrot Particle Editor v{APP_VERSION} [{BUILD_ID}]",
                        width=1280, height=800)
    _pos = os.environ.get("CARROT_WINPOS", "")
    try:
        _x, _y = (int(v) for v in _pos.split(","))
        dpg.set_viewport_pos([_x, _y])
    except Exception:
        pass
    try:
        ico = os.path.join(PS.app_base_dir(), "assets", "app_icon.ico")
        if os.path.isfile(ico):
            dpg.set_viewport_small_icon(ico)
            dpg.set_viewport_large_icon(ico)
    except Exception:
        pass
    apply_theme()
    load_fonts()
    build_ui()
    APP.sync_all()
    APP.sim.reset()
    APP.history_commit()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    APP._t_start = time.time()
    smoke = 0
    if "--smoke" in sys.argv:
        try:
            smoke = int(sys.argv[sys.argv.index("--smoke") + 1])
        except (ValueError, IndexError):
            smoke = 60
    n = 0
    while dpg.is_dearpygui_running():
        frame()
        dpg.render_dearpygui_frame()
        n += 1
        if smoke and n >= smoke:
            print(f"SMOKE-OK frames={n} parts={APP._n_show} fps={APP._fps}")
            break
    dpg.destroy_context()


if __name__ == "__main__":
    main()

