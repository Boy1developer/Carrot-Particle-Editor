# -*- coding: utf-8 -*-
"""Reusable drawlist widgets for trail settings (Dear PyGui).

CurveEditor: 0-1 plot with add/move/delete keys, per-key tangents,
presets, snap toggle, wheel Y-zoom. GradientEditor: draggable color
stops (below) + alpha stops (above) over a checkerboard bar, with
color edit for the selected stop, presets + reverse.

Rules: one drawlist per widget, redrawn only on change; a single
`onchange` fires on mouse-release (throttled to <=30 Hz while
dragging); no DPG items are created or deleted per frame.
"""
import time

try:
    import dearpygui.dearpygui as dpg
    _HAS_DPG = True
except Exception:
    dpg = None
    _HAS_DPG = False

import particle_studio as PS

CURVE_PRESETS = {
    "Constant": [[0.0, 1.0], [1.0, 1.0]],
    "Linear Down": [[0.0, 1.0, "linear"], [1.0, 0.0, "linear"]],
    "Ease Out": [[0.0, 1.0], [0.4, 0.7], [1.0, 0.0]],
    "Bell": [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]],
    "Spike": [[0.0, 0.0], [0.85, 0.0], [1.0, 1.0]],
    "Taper": [[0.0, 1.0], [0.7, 0.9], [1.0, 0.0]],
}
GRAD_PRESETS = {
    "White Fade": ([[0.0, "#ffffff"], [1.0, "#ffffff"]],
                   [[0.0, 255], [1.0, 0]]),
    "Fire": ([[0.0, "#ffee88"], [0.5, "#ff8800"], [1.0, "#ff2200"]],
             [[0.0, 255], [1.0, 0]]),
    "Ice": ([[0.0, "#d8f6ff"], [1.0, "#1e6fff"]],
            [[0.0, 255], [1.0, 40]]),
    "Neon": ([[0.0, "#aefcff"], [1.0, "#ff2fd6"]],
             [[0.0, 255], [1.0, 0]]),
}


def _norm_curve_keys(keys):
    out = []
    for k in keys or []:
        try:
            x, y = float(k[0]), float(k[1])
            m = str(k[2]).lower() if len(k) > 2 else "smooth"
            if m not in ("linear", "smooth", "constant"):
                m = "smooth"
            out.append([max(0.0, min(1.0, x)), y, m])
        except (ValueError, TypeError, IndexError):
            continue
    if not out:
        return [[0.0, 1.0, "smooth"], [1.0, 1.0, "smooth"]]
    return sorted(out, key=lambda k: k[0])


class CurveEditor:
    """Drawlist curve widget. value() -> [[x, y, mode]]."""

    W, H = 200, 110

    def __init__(self, tag, initial, onchange):
        self.tag = tag
        self.dl = tag + "_dl"
        self.keys = _norm_curve_keys(initial)
        self.onchange = onchange
        self.sel = -1
        self.ymax = 1.0
        self.snap = False
        self._drag = False
        self._last_fire = 0.0

    def value(self):
        return [list(k) for k in self.keys]

    def set_keys(self, keys):
        self.keys = _norm_curve_keys(keys)
        self.sel = -1
        self.redraw()

    # -- geometry --
    def _y_range(self):
        ys = [k[1] for k in self.keys] + [0.0, 1.0]
        return min(ys + [0.0]), max(ys + [1.0])

    def _to_px(self, x, y):
        lo, _hi = 0.0, max(1.0, self.ymax)
        px = 6 + x * (self.W - 12)
        py = 6 + (1.0 - (y - 0.0) / _hi) * (self.H - 12)
        return px, py

    def _to_val(self, px, py):
        _hi = max(1.0, self.ymax)
        x = max(0.0, min(1.0, (px - 6) / (self.W - 12)))
        y = max(0.0, (1.0 - (py - 6) / (self.H - 12)) * _hi)
        if self.snap:
            x = round(x * 20.0) / 20.0
            y = round(y * 20.0) / 20.0
        return x, y

    def _fire(self, force=False):
        now = time.time()
        if force or now - self._last_fire > 1.0 / 30.0:
            self._last_fire = now
            try:
                self.onchange(self.value())
            except Exception:
                pass

    # -- drawing (only this drawlist) --
    def redraw(self):
        if not _HAS_DPG:
            return
        try:
            dpg.delete_item(self.dl, children_only=True)
            dpg.draw_rectangle([0, 0], [self.W, self.H],
                               color=[53, 54, 70, 255],
                               fill=[20, 21, 28, 255], parent=self.dl)
            for gy in (0.25, 0.5, 0.75):
                _, py = self._to_px(0.0, gy * self.ymax)
                dpg.draw_line([6, py], [self.W - 6, py],
                              color=[44, 46, 68, 255], parent=self.dl)
            lut = PS.bake_curve([[k[0], k[1], k[2]] for k in self.keys], 48)
            pts = [self._to_px(i / 47.0, v) for i, v in enumerate(lut)]
            dpg.draw_polyline(pts, color=[123, 97, 255, 255], thickness=2,
                              parent=self.dl)
            for i, (x, y, m) in enumerate(self.keys):
                px, py = self._to_px(x, y)
                col = [255, 201, 60, 255] if i == self.sel else \
                    [232, 232, 238, 255]
                dpg.draw_circle([px, py], 5, color=col, thickness=2,
                                fill=[38, 39, 51, 255], parent=self.dl)
        except Exception:
            pass

    def _pick(self, mx, my):
        best, bd = -1, 10.0
        for i, (x, y, _m) in enumerate(self.keys):
            px, py = self._to_px(x, y)
            d = abs(mx - px) + abs(my - py)
            if d < bd:
                best, bd = i, d
        return best

    # -- mouse --
    def on_click(self, sender=None, app_data=None):
        try:
            mx, my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        try:
            btn = app_data[0] if isinstance(app_data, (list, tuple)) else 0
        except Exception:
            btn = 0
        hit = self._pick(mx, my)
        if btn == 1:  # right-click: remove key (keep >= 2)
            if hit >= 0 and len(self.keys) > 2:
                del self.keys[hit]
                self.sel = -1
                self.redraw()
                self._fire(force=True)
            return
        if hit >= 0:
            self.sel = hit
            self._drag = True
            try:
                dpg.set_value(self.tag + "_tan", self.keys[hit][2])
            except Exception:
                pass
            self.redraw()

    def on_dbl(self, sender=None, app_data=None):
        try:
            mx, my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        if self._pick(mx, my) < 0:
            x, y = self._to_val(mx, my)
            self.keys.append([x, y, "smooth"])
            self.keys.sort(key=lambda k: k[0])
            self.redraw()
            self._fire(force=True)

    def on_drag(self, sender=None, app_data=None):
        if not self._drag or not (0 <= self.sel < len(self.keys)):
            return
        try:
            mx, my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        x, y = self._to_val(mx, my)
        if self.sel == 0:
            x = 0.0
        if self.sel == len(self.keys) - 1:
            x = 1.0
        self.keys[self.sel][0] = x
        self.keys[self.sel][1] = y
        self.keys.sort(key=lambda k: k[0])
        self.redraw()
        self._fire()

    def on_release(self, sender=None, app_data=None):
        if self._drag:
            self._drag = False
            self.redraw()
            self._fire(force=True)

    def on_wheel(self, sender=None, app_data=None):
        try:
            d = float(app_data) if not isinstance(
                app_data, (list, tuple)) else float(app_data[1])
        except Exception:
            return
        self.ymax = max(0.2, min(8.0, self.ymax * (0.9 if d > 0 else 1.1)))
        self.redraw()

    def on_tangent(self, sender=None, app_data=None, *r):
        if 0 <= self.sel < len(self.keys) and app_data in (
                "linear", "smooth", "constant"):
            self.keys[self.sel][2] = app_data
            self.redraw()
            self._fire(force=True)

    def on_preset(self, sender=None, app_data=None, *r):
        name = app_data if isinstance(app_data, str) else None
        if name in CURVE_PRESETS:
            self.set_keys([list(k) for k in CURVE_PRESETS[name]])
            self._fire(force=True)

    def on_snap(self, sender=None, app_data=None, *r):
        self.snap = bool(app_data)

    def build(self, parent=None):
        if not _HAS_DPG:
            return
        kw = {"parent": parent} if parent else {}
        with dpg.group():
            dpg.add_drawlist(tag=self.dl, width=self.W, height=self.H,
                             **kw)
            with dpg.group(horizontal=True):
                for name in ("Constant", "Linear Down", "Ease Out"):
                    dpg.add_button(label=name, small=True,
                                   callback=lambda s, a, u=name: self.on_preset(
                                       s, u))
            with dpg.group(horizontal=True):
                for name in ("Bell", "Spike", "Taper"):
                    dpg.add_button(label=name, small=True,
                                   callback=lambda s, a, u=name: self.on_preset(
                                       s, u))
            with dpg.group(horizontal=True):
                dpg.add_text("Tangent")
                dpg.add_combo(tag=self.tag + "_tan",
                              items=["linear", "smooth", "constant"],
                              default_value="smooth", width=100,
                              callback=self.on_tangent)
                dpg.add_checkbox(label="Snap", callback=self.on_snap)
        with dpg.item_handler_registry(tag=self.dl + "_hr") as hr:
            dpg.add_item_clicked_handler(button=0, callback=self.on_click)
            dpg.add_item_clicked_handler(
                button=1, callback=self.on_click)
            dpg.add_item_double_clicked_handler(
                button=0, callback=self.on_dbl)
        dpg.bind_item_handler_registry(self.dl, self.dl + "_hr")
        self.redraw()


class GradientEditor:
    """Color stops (below bar) + alpha stops (above bar)."""

    W, BAR = 200, 26

    def __init__(self, tag, colors, alphas, onchange):
        self.tag = tag
        self.dl = tag + "_dl"
        self.colors = self._norm_c(colors)
        self.alphas = self._norm_a(alphas)
        self.onchange = onchange
        self.sel = ("c", 0)
        self._drag = False
        self._last_fire = 0.0

    @staticmethod
    def _norm_c(stops):
        out = []
        for s in stops or []:
            try:
                out.append([max(0.0, min(1.0, float(s[0]))), str(s[1])])
            except (ValueError, TypeError, IndexError):
                continue
        return sorted(out or [[0.0, "#ffffff"], [1.0, "#ffffff"]])

    @staticmethod
    def _norm_a(stops):
        out = []
        for s in stops or []:
            try:
                out.append([max(0.0, min(1.0, float(s[0]))),
                            max(0, min(255, int(float(s[1]))))])
            except (ValueError, TypeError, IndexError):
                continue
        return sorted(out or [[0.0, 255], [1.0, 0]])

    def value(self):
        return ([list(s) for s in self.colors],
                [list(s) for s in self.alphas])

    def set_stops(self, colors, alphas):
        self.colors = self._norm_c(colors)
        self.alphas = self._norm_a(alphas)
        self.sel = ("c", 0)
        self.redraw()

    def _fire(self, force=False):
        now = time.time()
        if force or now - self._last_fire > 1.0 / 30.0:
            self._last_fire = now
            try:
                self.onchange(*self.value())
            except Exception:
                pass

    def _bar_y(self):
        return 14

    def _to_px(self, x):
        return 6 + x * (self.W - 12)

    def redraw(self):
        if not _HAS_DPG:
            return
        try:
            dpg.delete_item(self.dl, children_only=True)
            by = self._bar_y()
            # checkerboard (alpha reference)
            for i in range(24):
                x0 = 6 + i * (self.W - 12) / 24.0
                x1 = 6 + (i + 1) * (self.W - 12) / 24.0
                fill = [200, 200, 200, 255] if i % 2 == 0 else \
                    [120, 120, 120, 255]
                dpg.draw_rectangle([x0, by], [x1, by + self.BAR],
                                   color=[0, 0, 0, 0], fill=fill,
                                   parent=self.dl)
            lut = PS.bake_gradient(self.colors, self.alphas, 48)
            for i, (r, g, b, _a) in enumerate(lut):
                x0 = 6 + i * (self.W - 12) / 48.0
                x1 = 6 + (i + 1) * (self.W - 12) / 48.0
                dpg.draw_rectangle([x0, by], [x1, by + self.BAR],
                                   color=[0, 0, 0, 0],
                                   fill=[r, g, b, 255], parent=self.dl)
            dpg.draw_rectangle([6, by], [self.W - 6, by + self.BAR],
                               color=[53, 54, 70, 255], thickness=1,
                               parent=self.dl)
            for j, (x, c) in enumerate(self.colors):
                px = self._to_px(x)
                col = [255, 201, 60, 255] if self.sel == ("c", j) else \
                    [232, 232, 238, 255]
                r, g, b = PS._parse_hex6(c)
                dpg.draw_circle([px, by + self.BAR + 9], 5, color=col,
                                thickness=2, fill=[r, g, b, 255],
                                parent=self.dl)
            for j, (x, _a) in enumerate(self.alphas):
                px = self._to_px(x)
                col = [255, 201, 60, 255] if self.sel == ("a", j) else \
                    [232, 232, 238, 255]
                dpg.draw_circle([px, by - 9], 5, color=col, thickness=2,
                                fill=[38, 39, 51, 255], parent=self.dl)
        except Exception:
            pass

    def _pick(self, mx, my):
        by = self._bar_y()
        best, bd, which = None, 9.0, None
        for j, (x, _c) in enumerate(self.colors):
            d = abs(mx - self._to_px(x)) + abs(my - (by + self.BAR + 9))
            if d < bd:
                best, bd, which = j, d, "c"
        for j, (x, _a) in enumerate(self.alphas):
            d = abs(mx - self._to_px(x)) + abs(my - (by - 9))
            if d < bd:
                best, bd, which = j, d, "a"
        return (which, best) if best is not None else (None, None)

    def on_click(self, sender=None, app_data=None):
        try:
            mx, my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        try:
            btn = app_data[0] if isinstance(app_data, (list, tuple)) else 0
        except Exception:
            btn = 0
        which, j = self._pick(mx, my)
        if btn == 1 and which is not None:  # right-click: remove
            arr = self.colors if which == "c" else self.alphas
            if len(arr) > 2:
                del arr[j]
                self.sel = ("c", 0)
                self.redraw()
                self._fire(force=True)
            return
        if which is not None:
            self.sel = (which, j)
            self._drag = True
            self._push_sel_widgets()
            self.redraw()

    def on_dbl(self, sender=None, app_data=None):
        try:
            mx, _my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        which, j = self._pick(mx, _my)
        if which is None:
            x = max(0.0, min(1.0, (mx - 6) / (self.W - 12)))
            self.colors.append([x, "#ffffff"])
            self.colors.sort()
            self.sel = ("c", [s[0] for s in self.colors].index(x))
            self.redraw()
            self._fire(force=True)

    def on_drag(self, sender=None, app_data=None):
        if not self._drag:
            return
        which, j = self.sel
        arr = self.colors if which == "c" else self.alphas
        if not (0 <= j < len(arr)):
            return
        try:
            mx, _my = (float(v) for v in dpg.get_drawing_mouse_pos())
        except Exception:
            return
        arr[j][0] = max(0.0, min(1.0, (mx - 6) / (self.W - 12)))
        arr.sort()
        self.redraw()
        self._fire()

    def on_release(self, sender=None, app_data=None):
        if not self._drag:
            return
        # drag-off deletes (released far outside the widget)
        try:
            mx, my = (float(v) for v in dpg.get_drawing_mouse_pos())
            outside = mx < -20 or mx > self.W + 20 or my < -30 or \
                my > self._bar_y() + self.BAR + 30
        except Exception:
            outside = False
        which, j = self.sel
        arr = self.colors if which == "c" else self.alphas
        if outside and len(arr) > 2 and 0 <= j < len(arr):
            del arr[j]
            self.sel = ("c", 0)
        self._drag = False
        self.redraw()
        self._fire(force=True)

    def _push_sel_widgets(self):
        try:
            which, j = self.sel
            if which == "c":
                r, g, b = PS._parse_hex6(self.colors[j][1])
                dpg.set_value(self.tag + "_pick",
                              [r / 255.0, g / 255.0, b / 255.0, 255])
            else:
                dpg.set_value(self.tag + "_aval", self.alphas[j][1])
        except Exception:
            pass

    def on_pick(self, sender=None, app_data=None, *r):
        try:
            which, j = self.sel
            if which == "c":
                r, g, b, _a = (int(float(v) * 255) for v in app_data[:4])
                self.colors[j][1] = "#%02x%02x%02x" % (r, g, b)
                self.redraw()
                self._fire(force=True)
        except Exception:
            pass

    def on_alpha(self, sender=None, app_data=None, *r):
        try:
            which, j = self.sel
            if which == "a":
                self.alphas[j][1] = max(0, min(255, int(app_data)))
                self.redraw()
                self._fire(force=True)
        except Exception:
            pass

    def on_preset(self, sender=None, app_data=None, *r):
        name = app_data if isinstance(app_data, str) else None
        if name in GRAD_PRESETS:
            c, a = GRAD_PRESETS[name]
            self.set_stops([list(s) for s in c], [list(s) for s in a])
            self._fire(force=True)

    def on_reverse(self, sender=None, app_data=None, *r):
        self.colors = [[1.0 - x, c] for x, c in reversed(self.colors)]
        self.alphas = [[1.0 - x, a] for x, a in reversed(self.alphas)]
        self.redraw()
        self._fire(force=True)

    def build(self, parent=None):
        if not _HAS_DPG:
            return
        with dpg.group():
            dpg.add_drawlist(tag=self.dl, width=self.W,
                             height=self._bar_y() + self.BAR + 28)
            with dpg.group(horizontal=True):
                dpg.add_color_edit(tag=self.tag + "_pick",
                                   default_value=[255, 255, 255, 255],
                                   width=80, callback=self.on_pick)
                dpg.add_input_int(tag=self.tag + "_aval", default_value=255,
                                  width=-1, step=1, step_fast=10,
                                  callback=self.on_alpha)
            with dpg.group(horizontal=True):
                for name in ("White Fade", "Fire", "Ice"):
                    dpg.add_button(label=name, small=True,
                                   callback=lambda s, a, u=name: self.on_preset(
                                       s, u))
            with dpg.group(horizontal=True):
                dpg.add_button(label="Neon", small=True,
                               callback=lambda s, a: self.on_preset(
                                   s, "Neon"))
                dpg.add_button(label="Reverse", small=True,
                               callback=self.on_reverse)
        with dpg.item_handler_registry(tag=self.dl + "_hr") as hr:
            dpg.add_item_clicked_handler(button=0, callback=self.on_click)
            dpg.add_item_clicked_handler(button=1, callback=self.on_click)
            dpg.add_item_double_clicked_handler(button=0,
                                                callback=self.on_dbl)
        dpg.bind_item_handler_registry(self.dl, self.dl + "_hr")
        self.redraw()
