# -*- coding: utf-8 -*-
"""Trail template browser (Dear PyGui glue over the C++ registry).

Language-split rule: Python builds widgets, handles clicks/keys, and
copies C++ results into widgets (set_value/configure_item). All search,
merge, validation, LUTs, thumbnails and preset files live in C++ inside
`particle_core`. If the compiled core lacks the template API, a tiny
pure-Python FALLBACK (clearly marked) loads JSON + merges so the app
never crashes; C++ stays the source of truth.
"""
import copy
import glob
import json
import os
import time

try:
    import dearpygui.dearpygui as dpg
    _HAS_DPG = True
except Exception:
    dpg = None
    _HAS_DPG = False

import particle_studio as PS

try:
    import particle_core as _CORE
    HAS_TPL = all(hasattr(_CORE, n) for n in (
        "templates_init", "templates_register", "templates_list",
        "templates_info", "templates_apply", "templates_thumbnail",
        "templates_texture", "templates_fav", "presets_save",
        "presets_delete"))
except Exception:
    _CORE = None
    HAS_TPL = False

# Late-bound studio context (set by studio_imgui after import).
C = {}


def init_ctx(**kw):
    C.update(kw)


CATS = [("combat", "Combat & Weapons"),
        ("magic", "Magic & Energy"),
        ("movement", "Movement & Vehicles"),
        ("nature", "Nature & Elements"),
        ("stylized", "Stylized & Tools")]
CAT_IDS = [c for c, _ in CATS]

FALLBACK_REG = {}  # id -> template dict (only when C++ API missing)


def user_dir():
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        p = os.path.join(base, "CarrotParticleEditor", "trail_presets")
        os.makedirs(p, exist_ok=True)
        return p
    except Exception:
        return ""


def builtin_dir():
    return os.path.join(PS.app_base_dir(), "assets", "presets", "trails")


def _schema_payload():
    return [{"key": f["key"], "type": f["type"],
             "min": f.get("min", 0), "max": f.get("max", 1),
             "items": list(f.get("items", []))} for f in PS.TRAIL_SCHEMA]


def startup():
    """Init registry + load builtin and user templates. Returns (n, ms)."""
    t0 = time.time()
    udir = user_dir()
    if HAS_TPL:
        _CORE.templates_init(_schema_payload(), udir)
    n = 0
    for root, is_user in ((builtin_dir(), False), (udir, True)):
        try:
            files = sorted(glob.glob(os.path.join(root, "**", "*.json"),
                                     recursive=True))
        except Exception:
            files = []
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                tid = os.path.splitext(os.path.basename(path))[0]
                if HAS_TPL:
                    w = _CORE.templates_register(tid, data, is_user)
                    if w:
                        PS.debug_log("TPL-SKIP", tid, str(w)[:200])
                        continue
                else:
                    FALLBACK_REG[tid] = data
                n += 1
            except Exception as e:
                PS.debug_log("TPL-SKIP", path, repr(e)[:200])
    return n, (time.time() - t0) * 1000.0


# ---- fallback (C++ missing): minimal merge, NOT the source of truth ----
def _fb_apply(tid, mode, defaults, current):
    data = FALLBACK_REG.get(tid, {})
    merged = PS.sanitize_trails(defaults)
    src = data.get("settings", {})
    ov = data.get("overrides_3d" if mode == "3d" else "overrides_2d", {})
    for k in list(merged):
        if k in src:
            merged[k] = src[k]
        if k in ov:
            merged[k] = ov[k]
    merged = PS.sanitize_trails(merged)
    changed = [k for k in merged
               if json.dumps(merged[k], sort_keys=True) != json.dumps(
                   current.get(k), sort_keys=True)]
    return merged, changed


# ---- popup state (built once, shown/hidden) ----
_BUILT = False
_CARDS = {}      # tid -> card group tag
_CAT = "combat"
_QUERY = ""
_APPLIED = ""
_TEX_TAGS = {}   # kind -> dpg texture tag


def _thumb_tag(tid):
    return "tpl_thumb_" + "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in tid)


def _ensure_thumb(tid):
    """Upload the C++ thumbnail once; placeholder text until then."""
    if not (HAS_TPL and _HAS_DPG):
        return False
    try:
        if tid in _TEX_TAGS:
            return True
        w, h, buf = _CORE.templates_thumbnail(tid, 96, 48)
        floats = [b / 255.0 for b in buf]
        with dpg.texture_registry():
            tag = _thumb_tag(tid)
            dpg.add_static_texture(w, h, floats, tag=tag)
        _TEX_TAGS[tid] = tag
        return True
    except Exception:
        return False


def _card_tags(tid):
    s = "".join(c if (c.isalnum() or c in "-_") else "_" for c in tid)
    return "tpl_card_" + s, "tpl_name_" + s


def _build_cards(cat):
    """Build this category's cards once (2-column grid)."""
    from studio_imgui import MUTED  # local: studio owns the palette
    try:
        ids = _CORE.templates_list(cat, "", _mode(), "name", False) \
            if HAS_TPL else sorted(
                t for t, d in FALLBACK_REG.items()
                if d.get("category", "stylized") == cat)
    except Exception:
        ids = []
    host = "tpl_cards_" + cat
    for row in range(0, len(ids), 2):
        with dpg.group(horizontal=True, parent=host):
            for tid in ids[row:row + 2]:
                _build_card(tid, cat)


def _build_card(tid, cat):
    from studio_imgui import MUTED
    card, name_tag = _card_tags(tid)
    try:
        info = _CORE.templates_info(tid) if HAS_TPL else {
            "name": FALLBACK_REG.get(tid, {}).get("name", tid),
            "description": FALLBACK_REG.get(tid, {}).get("description", ""),
            "tags": FALLBACK_REG.get(tid, {}).get("tags", []),
            "modes": FALLBACK_REG.get(tid, {}).get("modes", ["2d", "3d"]),
            "texture": FALLBACK_REG.get(tid, {}).get("texture") or "",
            "user": False}
    except Exception:
        return
    ok_mode = _mode() in (info.get("modes") or ["2d", "3d"])
    is_user = bool(info.get("user"))
    with dpg.group(tag=card, width=200):
        dpg.add_text(info.get("name", tid), tag=name_tag,
                     color=list(MUTED) + [255])
        dpg.add_text(str(info.get("description", ""))[:64],
                     color=list(MUTED) + [255], wrap=190)
        dpg.add_text(" ".join("#" + str(t)
                              for t in (info.get("tags") or [])[:3]),
                     color=list(MUTED) + [255], wrap=190)
        dpg.add_button(label="Apply", width=190, enabled=ok_mode,
                       callback=lambda *a, u=tid: apply_template(u, False))
        dpg.add_button(label="Apply & Close", width=190, enabled=ok_mode,
                       callback=lambda *a, u=tid: apply_template(u, True))
        if is_user:
            dpg.add_button(label="Delete", width=190,
                           callback=lambda *a, u=tid: _delete_user(u))
        if not ok_mode:
            with dpg.tooltip(card):
                dpg.add_text("Mode-specific: not for " + _mode().upper())
    try:
        with dpg.item_handler_registry(tag=card + "_hr") as hr:
            dpg.add_item_double_clicked_handler(
                button=0,
                callback=lambda *a, u=tid: apply_template(u, True))
        dpg.bind_item_handler_registry(card, card + "_hr")
    except Exception:
        pass
    _CARDS[tid] = card
    _refresh_thumb(tid)


def _refresh_thumb(tid):
    if tid not in _CARDS:
        return
    if _ensure_thumb(tid):
        try:
            kids = dpg.get_item_children(_CARDS[tid], 1) or []
            kw = {"before": kids[0]} if kids else {}
            dpg.add_image(_TEX_TAGS[tid], width=190, height=95,
                          parent=_CARDS[tid], **kw)
        except Exception:
            pass


def _mode():
    try:
        return C.get("get_ptype", lambda: "2d")()
    except Exception:
        return "2d"


def open_popup(cat="combat"):
    global _BUILT, _CAT
    if not _HAS_DPG:
        return
    _CAT = cat if cat in CAT_IDS + ["all", "user"] else "combat"
    if not _BUILT:
        _build_popup()
        _BUILT = True
    refresh_list()
    try:
        dpg.configure_item("trail_tpl_win", show=True)
    except Exception:
        pass


def close_popup():
    try:
        dpg.configure_item("trail_tpl_win", show=False)
    except Exception:
        pass


def _build_popup():
    from studio_imgui import MUTED, OK
    with dpg.window(tag="trail_tpl_win", label="Templates", modal=True,
                    show=False, width=480, height=560, pos=[400, 120]):
        with dpg.group(horizontal=True):
            dpg.add_text("Templates — ", color=list(MUTED) + [255])
            dpg.add_combo(tag="tpl_cat", items=["all"] + CAT_IDS + ["user"],
                          default_value=_CAT, width=150,
                          callback=_on_cat)
            dpg.add_button(label="X", width=30,
                           callback=lambda *a: close_popup())
        dpg.add_input_text(tag="tpl_search", hint="search name / tag…",
                           width=-1, callback=_on_search)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Favs", tag="tpl_favs",
                             callback=lambda *a: refresh_list())
            dpg.add_combo(tag="tpl_sort", items=["name", "recent"],
                          default_value="name", width=100,
                          callback=lambda *a: refresh_list())
            dpg.add_text("", tag="tpl_status", color=list(OK) + [255])
        for c in CAT_IDS + ["user", "all"]:
            with dpg.group(tag="tpl_cards_" + c, show=(c == _CAT)):
                pass
        with dpg.group(tag="tpl_user_row", horizontal=True, show=False):
            dpg.add_input_text(tag="tpl_user_name", hint="preset name…",
                               width=200)
            dpg.add_button(label="Save current", width=120,
                           callback=lambda *a: _save_user())
            dpg.add_button(label="Delete", width=80,
                           callback=lambda *a: _delete_user_sel())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Reset to defaults", width=150,
                           callback=lambda *a: _reset_defaults())
            dpg.add_button(label="Apply & Close", width=150,
                           callback=lambda *a: close_popup())
        dpg.add_text("My Presets: use the sidebar Save button; "
                     "hover a user card for Delete.",
                     color=list(MUTED) + [255], wrap=440)


def _on_cat(sender=None, app_data=None, *r):
    global _CAT
    _CAT = str(app_data or "combat")
    refresh_list()


def _on_search(sender=None, app_data=None, *r):
    global _QUERY
    _QUERY = str(app_data or "")
    refresh_list()


def refresh_list():
    """Show this category (build cards lazily); filter via show/hide."""
    if not _HAS_DPG:
        return
    try:
        dpg.set_value("tpl_cat", _CAT)
    except Exception:
        pass
    for c in CAT_IDS + ["user", "all"]:
        try:
            dpg.configure_item("tpl_cards_" + c, show=(c == _CAT))
        except Exception:
            pass
    try:
        dpg.configure_item("tpl_user_row", show=(_CAT == "user"))
    except Exception:
        pass
    host_empty = True
    try:
        host_empty = dpg.get_item_children("tpl_cards_" + _CAT, 1) in (
            None, [], {})
    except Exception:
        pass
    if host_empty and _CAT not in ("all",):
        _build_cards(_CAT)
    try:
        favs = bool(dpg.get_value("tpl_favs"))
        sort = str(dpg.get_value("tpl_sort") or "name")
    except Exception:
        favs, sort = False, "name"
    try:
        ids = _CORE.templates_list(
            "" if _CAT == "all" else _CAT, _QUERY, _mode(), sort, favs) \
            if HAS_TPL else None
    except Exception:
        ids = None
    if ids is None:  # fallback or "all": match locally
        ids = []
        src = FALLBACK_REG if not HAS_TPL else {}
        for tid, d in (src.items() if src else []):
            if _CAT not in ("all",) and d.get("category") != _CAT:
                continue
            q = _QUERY.lower()
            hay = (str(d.get("name", "")) + " " + str(
                d.get("description", "")) + " " + " ".join(
                d.get("tags", []))).lower()
            if q and q not in hay:
                continue
            ids.append(tid)
    want = set(ids)
    for tid, card in list(_CARDS.items()):
        try:
            dpg.configure_item(card, show=(tid in want))
        except Exception:
            pass


def _save_user():
    try:
        name = "".join(
            c if (c.isalnum() or c in ("_", "-")) else "_"
            for c in str(dpg.get_value("tpl_user_name") or ""))[:48]
        if not name:
            return
        cur = dict(C["get_trails"]())
        if HAS_TPL:
            path = _CORE.presets_save(
                name, cur, {"name": name, "category": "user"})
            _CORE.templates_register(
                name, {"id": name, "name": name, "category": "user",
                       "description": "", "tags": ["user"],
                       "modes": ["2d", "3d"], "settings": cur}, True)
        else:
            FALLBACK_REG[name] = {"id": name, "name": name,
                                  "category": "user", "description": "",
                                  "tags": ["user"], "modes": ["2d", "3d"],
                                  "settings": cur}
        C["status"]("Preset saved: " + name)
        refresh_list()
    except Exception as e:
        PS.debug_log("TPL-SAVE-EXC", repr(e)[:200])


def _delete_user(tid):
    try:
        if HAS_TPL:
            _CORE.presets_delete(tid)
        else:
            FALLBACK_REG.pop(tid, None)
        try:
            if tid in _CARDS:
                dpg.delete_item(_CARDS.pop(tid))
        except Exception:
            pass
        refresh_list()
    except Exception as e:
        PS.debug_log("TPL-DEL-EXC", repr(e)[:200])


def _delete_user_sel():
    _delete_user(str(dpg.get_value("tpl_user_name") or ""))


def _reset_defaults():
    try:
        C["reset_trails"]()
    except Exception:
        pass


def apply_template(tid, close_after):
    """ONE core call -> changed widgets -> dirty once -> one undo step."""
    global _APPLIED
    t0 = time.time()
    try:
        mode = _mode()
        cur = dict(C["get_trails"]())
        if HAS_TPL:
            new, changed = _CORE.templates_apply(
                tid, mode, PS.default_trails(), cur)
        else:
            new, changed = _fb_apply(
                tid, mode, PS.default_trails(), cur)
        C["set_trails"](new)
        C["sync_changed"](changed)
        C["rebake"]()
        C["reset_sim"]()
        C["dirty"]()
        C["commit"]("Apply template: " + tid)
        _APPLIED = tid
        try:
            info = _CORE.templates_info(tid) if HAS_TPL else {"name": tid}
            C["status"]("Applied: " + str(info.get("name", tid)))
            _apply_texture(info)
        except Exception:
            pass
        ms = (time.time() - t0) * 1000.0
        PS.debug_log("TPL-APPLY", tid, "changed=%d" % len(changed),
                     "%.2fms" % ms)
    except Exception as e:
        PS.debug_log("TPL-APPLY-EXC", tid, repr(e)[:200])
    if close_after:
        close_popup()
    else:
        refresh_list()


def _apply_texture(info):
    """Procedural texture for the editor preview (white fallback + warn)."""
    tex = (info.get("texture") or "") if isinstance(info, dict) else ""
    if not tex:
        return
    try:
        kind = str(tex).split(":")[0] if ":" in str(tex) else str(tex)
        if kind not in ("glow", "dots", "stripes", "flame", "crystal"):
            PS.debug_log("TPL-TEX-MISSING", str(tex)[:80])
            return
        if not HAS_TPL:
            return
        w, h, buf = _CORE.templates_texture(kind, 64, 64)
        floats = [b / 255.0 for b in buf]
        try:
            if dpg.does_item_exist("trail_tpl_tex"):
                dpg.delete_item("trail_tpl_tex")
            with dpg.texture_registry():
                dpg.add_static_texture(w, h, floats, tag="trail_tpl_tex")
        except Exception:
            pass
    except Exception as e:
        PS.debug_log("TPL-TEX-EXC", repr(e)[:160])
