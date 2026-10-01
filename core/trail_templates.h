// trail_templates.h — C++ trail template registry (header-only).
//
// Included by core/particle_core.cpp so the core stays one translation unit
// (MSVC / g++ / clang++ / Zig all keep working with zero build changes
// beyond watching this header for staleness).
//
// Split of duties: Python reads JSON files (stdlib) and hands dicts over;
// EVERYTHING else lives here: schema-driven validation, storage in compact
// POD structs, text/tag/category/mode search, favorites/recents, settings
// merge (defaults + template + 2D/3D overrides) with clamping, changed-field
// detection, curve/gradient LUT baking (reuses TrailCfg tables), procedural
// texture + thumbnail RGBA buffers, and user-preset serialization.
//
// Binding style matches the core: raw CPython C API, flat return values
// (lists/dicts/bytes), no nested-object walks on the Python side.
#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace trailpub {

// ---- schema (passed once from Python, the single source of truth) ----
enum FieldType { FT_BOOL = 0, FT_INT, FT_FLOAT, FT_COMBO, FT_TEXT, FT_CURVE, FT_GRAD };

struct FieldSpec {
    std::string key;
    FieldType type = FT_FLOAT;
    double lo = 0, hi = 1;
    std::vector<std::string> items;  // combos
};

static std::string lower_of(const std::string &s) {
    std::string o = s;
    for (char &c : o) c = (char)tolower((unsigned char)c);
    return o;
}

// ---- stored key lists: numeric (widthCurve) or string-valued (gradients) --
struct KeyList {
    std::vector<double> x;
    std::vector<double> ynum;          // numeric y (widthCurve, alphaStops)
    std::vector<std::string> ystr;     // string y (colorStops)
    std::vector<int> mode;             // 0 linear, 1 smooth, 2 constant
    bool numeric = true;
};

// ---- one validated setting value ----
struct Setting {
    int spec = -1;
    double num = 0;
    std::string str;
    KeyList keys;
    bool isKeys = false;
};

struct Template {
    std::string id, name, category, description, texture;
    std::vector<std::string> tags;
    int modes = 3;  // bit0 = 2d, bit1 = 3d
    int version = 1;
    bool user = false;
    std::vector<Setting> settings;       // partial (template data)
    std::vector<Setting> overrides2d;
    std::vector<Setting> overrides3d;
};

struct Registry {
    std::vector<FieldSpec> schema;
    std::vector<Template> items;
    std::vector<std::string> favs;
    std::vector<std::string> recents;
    std::string userDir;
    // thumbnail/texture caches: id -> RGBA bytes (+ sizes)
    struct Blob { std::string id; int w = 0, h = 0; std::vector<unsigned char> px; };
    std::vector<Blob> thumbs;
    std::vector<Blob> texcache;

    const FieldSpec *spec_of(const std::string &key) const {
        for (auto &f : schema)
            if (f.key == key) return &f;
        return nullptr;
    }
    int index_of(const std::string &id) const {
        for (size_t i = 0; i < items.size(); i++)
            if (items[i].id == id) return (int)i;
        return -1;
    }
};

static Registry g_reg;

// ---- validation: dict -> validated Setting list (unknown keys dropped) ---
static bool parse_keylist(PyObject *v, bool numeric, KeyList &out) {
    out = KeyList();
    out.numeric = numeric;
    if (!v || !PyList_Check(v)) return false;
    struct Raw { double x; double yn; std::string ys; int m; };
    std::vector<Raw> tmp;
    for (Py_ssize_t i = 0; i < PyList_Size(v); i++) {
        PyObject *k = PyList_GetItem(v, i);  // borrowed
        if (!k || !PyList_Check(k) || PyList_Size(k) < 2) continue;
        double x = PyFloat_AsDouble(PyList_GetItem(k, 0));
        if (PyErr_Occurred()) { PyErr_Clear(); continue; }
        int m = 1;
        if (PyList_Size(k) > 2) {
            PyObject *om = PyList_GetItem(k, 2);
            if (om && PyUnicode_Check(om)) {
                const char *s = PyUnicode_AsUTF8(om);
                if (s && !strcmp(s, "linear")) m = 0;
                else if (s && !strcmp(s, "constant")) m = 2;
            }
        }
        Raw r{x, 0.0, "", m};
        PyObject *oy = PyList_GetItem(k, 1);
        if (numeric) {
            r.yn = PyFloat_AsDouble(oy);
            if (PyErr_Occurred()) { PyErr_Clear(); continue; }
        } else {
            if (!oy || !PyUnicode_Check(oy)) continue;
            const char *s = PyUnicode_AsUTF8(oy);
            r.ys = s ? s : "";
        }
        tmp.push_back(r);
    }
    std::sort(tmp.begin(), tmp.end(),
              [](const Raw &a, const Raw &b) { return a.x < b.x; });
    for (auto &r : tmp) {
        out.x.push_back(r.x);
        out.mode.push_back(r.m);
        if (numeric) out.ynum.push_back(r.yn);
        else out.ystr.push_back(r.ys);
    }
    return !out.x.empty();
}

static bool validate_block(PyObject *d, const Registry &reg,
                           std::vector<Setting> &out, std::string &warn) {
    out.clear();
    if (!d || !PyDict_Check(d)) return true;
    PyObject *k = nullptr, *v = nullptr;
    Py_ssize_t pos = 0;
    while (PyDict_Next(d, &pos, &k, &v)) {
        if (!PyUnicode_Check(k)) continue;
        const char *ks = PyUnicode_AsUTF8(k);
        if (!ks) continue;
        const FieldSpec *sp = reg.spec_of(ks);
        if (!sp) continue;  // unknown fields dropped (forward compatible)
        Setting s;
        s.spec = (int)(sp - reg.schema.data());
        bool ok = true;
        switch (sp->type) {
            case FT_BOOL: {
                int b = PyObject_IsTrue(v);
                if (b < 0) { PyErr_Clear(); ok = false; break; }
                s.num = b ? 1.0 : 0.0;
                break;
            }
            case FT_INT: {
                long x = PyLong_AsLong(v);
                if (PyErr_Occurred()) {
                    double f = PyFloat_AsDouble(v);
                    if (PyErr_Occurred()) { PyErr_Clear(); ok = false; break; }
                    x = (long)f;
                }
                s.num = std::min(sp->hi, std::max(sp->lo, (double)x));
                break;
            }
            case FT_FLOAT: {
                double x = PyFloat_AsDouble(v);
                if (PyErr_Occurred()) { PyErr_Clear(); ok = false; break; }
                if (!(x == x)) { ok = false; break; }  // NaN rejected
                s.num = std::min(sp->hi, std::max(sp->lo, x));
                break;
            }
            case FT_COMBO: {
                if (!PyUnicode_Check(v)) { ok = false; break; }
                const char *sv = PyUnicode_AsUTF8(v);
                std::string got = sv ? sv : "";
                bool hit = false;
                for (auto &it : sp->items)
                    if (it == got) { hit = true; break; }
                if (!hit) { ok = false; break; }
                s.str = got;
                break;
            }
            case FT_TEXT: {
                if (!PyUnicode_Check(v)) { ok = false; break; }
                const char *sv = PyUnicode_AsUTF8(v);
                s.str = sv ? sv : "";
                break;
            }
            case FT_CURVE: {
                KeyList kl;
                if (!parse_keylist(v, true, kl)) { ok = false; break; }
                s.keys = kl;
                s.isKeys = true;
                break;
            }
            case FT_GRAD: {
                KeyList kl;
                // color stops carry strings, alpha stops numbers: accept both
                if (!parse_keylist(v, true, kl)) {
                    if (!parse_keylist(v, false, kl)) { ok = false; break; }
                }
                s.keys = kl;
                s.isKeys = true;
                break;
            }
        }
        if (ok) out.push_back(s);
        else { warn += std::string("bad value for '") + ks + "'; "; }
    }
    return true;
}

// ---- merge: defaults + settings + mode overrides -> complete POD --------
struct Merged {
    std::vector<Setting> all;  // one entry per schema field, schema order
};

static void merge_settings(const Registry &reg, const Template &t,
                           bool is3d, PyObject *defaults, Merged &m) {
    m.all.clear();
    for (size_t i = 0; i < reg.schema.size(); i++) {
        Setting s;
        s.spec = (int)i;
        const FieldSpec &sp = reg.schema[i];
        // defaults from the passed trails dict
        PyObject *dv = defaults ? PyDict_GetItemString(defaults, sp.key.c_str()) : nullptr;
        if (sp.type == FT_BOOL) {
            int b = dv ? PyObject_IsTrue(dv) : 0;
            if (b < 0) { PyErr_Clear(); b = 0; }
            s.num = b ? 1.0 : 0.0;
        } else if (sp.type == FT_INT || sp.type == FT_FLOAT) {
            double x = dv ? PyFloat_AsDouble(dv) : 0.0;
            if (PyErr_Occurred()) { PyErr_Clear(); x = 0.0; }
            if (!(x == x)) x = 0.0;
            s.num = std::min(sp.hi, std::max(sp.lo, x));
        } else if (sp.type == FT_COMBO || sp.type == FT_TEXT) {
            if (dv && PyUnicode_Check(dv)) {
                const char *sv = PyUnicode_AsUTF8(dv);
                s.str = sv ? sv : "";
            }
        } else {
            KeyList kl;
            bool numeric = (sp.key == "widthCurve" ||
                            sp.key == "alphaStops" ||
                            sp.key == "lifeAlphaStops");
            if (dv && parse_keylist(dv, numeric, kl)) s.keys = kl;
            s.isKeys = true;
        }
        // template settings win, then the mode override
        for (auto &o : t.settings)
            if (o.spec == (int)i) s = o;
        const std::vector<Setting> &ov = is3d ? t.overrides3d : t.overrides2d;
        for (auto &o : ov)
            if (o.spec == (int)i) s = o;
        m.all.push_back(s);
    }
}

// ---- search: query + category + mode + fav/recent flags ------------------
static bool match_query(const Template &t, const std::string &q) {
    if (q.empty()) return true;
    std::string hay = lower_of(t.name + " " + t.description + " " + t.id);
    for (auto &tg : t.tags) hay += " " + lower_of(tg);
    return hay.find(q) != std::string::npos;
}

// ---- procedural RGBA (glow / dots / stripes / sheets), cached -----------
static std::vector<unsigned char> proc_texture(const std::string &kind, int w, int h) {
    std::vector<unsigned char> px((size_t)w * h * 4, 0);
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            double u = (x + 0.5) / w, v = (y + 0.5) / h;
            double r = 0, g = 0, b = 0, a = 0;
            if (kind == "dots") {
                double cx = (u * 4 - (int)(u * 4)) - 0.5, cy = v - 0.5;
                double d = sqrt(cx * cx * 4.0 + cy * cy);
                a = d < 0.32 ? 255 : 0; r = g = b = 255;
            } else if (kind == "stripes") {
                double s = 0.5 + 0.5 * sin(u * 25.1327);
                a = 140 + 115 * s; r = 140; g = 220; b = 255;
            } else if (kind == "flame") {
                int cell = (int)(u * 4) + 4 * (int)(v * 4);
                double f = 0.5 + 0.5 * sin(cell * 12.9898 + u * 40.0 + v * 31.0);
                a = 200; r = 255; g = 120 + 100 * f; b = 30;
            } else if (kind == "crystal") {
                int cell = (int)(u * 4) + 4 * (int)(v * 2);
                double f = 0.5 + 0.5 * sin(cell * 78.233 + v * 20.0);
                a = 200; r = 160 + 60 * f; g = 220; b = 255;
            } else {  // glow: soft radial falloff
                double dx = u - 0.5, dy = v - 0.5;
                double d = sqrt(dx * dx + dy * dy) * 2.0;
                a = d >= 1.0 ? 0 : 255 * (1.0 - d * d);
                r = g = b = 255;
            }
            size_t o = ((size_t)y * w + x) * 4;
            px[o] = (unsigned char)r; px[o + 1] = (unsigned char)g;
            px[o + 2] = (unsigned char)b; px[o + 3] = (unsigned char)(a < 0 ? 0 : a > 255 ? 255 : a);
        }
    }
    return px;
}

// ---- minimal JSON writer for the known schema (user presets) -------------
static std::string json_esc(const std::string &s) {
    std::string o;
    for (char c : s) {
        if (c == '"') o += "\\\"";
        else if (c == '\\') o += "\\\\";
        else if (c == '\n') o += "\\n";
        else o += c;
    }
    return o;
}

}  // namespace trailpub
