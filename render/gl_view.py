# -*- coding: utf-8 -*-
"""Offscreen GPU particle renderer embedded in the tkinter editor.

Hidden GLFW context + hand-rolled ctypes OpenGL 3.3 (no PyOpenGL/numpy, so it
installs everywhere incl. Python 3.14). Renders background + grid + particles
(OPAQUE) -> raw PPM bytes; tkinter shows them under its guide/gizmo items.

Projection uses a custom clip matrix that matches StudioApp._proj EXACTLY
(verified numerically), so GL dots align 1:1 with tkinter guides.
Any failure -> .ok=False and the app falls back to plain canvas items.
"""
import ctypes
import math
import struct
from array import array

GL_FALSE = 0
GL_UNSIGNED_BYTE = 0x1401
GL_FLOAT = 0x1406
GL_RGB = 0x1907
GL_RGBA = 0x1908
GL_RGBA8 = 0x8058
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_BLEND = 0x0BE2
GL_ZERO = 0
GL_ONE = 1
GL_SRC_COLOR = 0x0300
GL_ONE_MINUS_SRC_COLOR = 0x0301
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_DST_ALPHA = 0x0304
GL_ONE_MINUS_DST_ALPHA = 0x0305
GL_DST_COLOR = 0x0306
GL_ONE_MINUS_DST_COLOR = 0x0307
GL_FUNC_ADD = 0x8006
GL_FUNC_SUBTRACT = 0x800A
GL_FUNC_REVERSE_SUBTRACT = 0x800B
GL_MAX = 0x8008
GL_ARRAY_BUFFER = 0x8892
GL_DYNAMIC_DRAW = 0x88E8
GL_STATIC_DRAW = 0x88E4
GL_VERTEX_SHADER = 0x8B31
GL_FRAGMENT_SHADER = 0x8B30
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82
GL_FRAMEBUFFER = 0x8D40
GL_RENDERBUFFER = 0x8D41
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_DEPTH_COMPONENT16 = 0x81A5
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_LINEAR = 0x2601
GL_PACK_ALIGNMENT = 0x0D05

_FUNCS = {
    "glGetString": (ctypes.c_char_p, (ctypes.c_uint,)),
    "glClearColor": (None, (ctypes.c_float,) * 4),
    "glClear": (None, (ctypes.c_uint,)),
    "glViewport": (None, (ctypes.c_int,) * 4),
    "glEnable": (None, (ctypes.c_uint,)),
    "glDisable": (None, (ctypes.c_uint,)),
    "glBlendFunc": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glBlendEquation": (None, (ctypes.c_uint,)),
    "glDepthMask": (None, (ctypes.c_ubyte,)),
    "glGenVertexArrays": (None, (ctypes.c_int, ctypes.c_void_p)),
    "glBindVertexArray": (None, (ctypes.c_uint,)),
    "glGenBuffers": (None, (ctypes.c_int, ctypes.c_void_p)),
    "glBindBuffer": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glBufferData": (None, (ctypes.c_uint, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint)),
    "glVertexAttribPointer": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
                                     ctypes.c_ubyte, ctypes.c_int, ctypes.c_void_p)),
    "glEnableVertexAttribArray": (None, (ctypes.c_uint,)),
    "glVertexAttribDivisor": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glUseProgram": (None, (ctypes.c_uint,)),
    "glGetUniformLocation": (ctypes.c_int, (ctypes.c_uint, ctypes.c_char_p)),
    "glUniformMatrix4fv": (None, (ctypes.c_int, ctypes.c_int, ctypes.c_ubyte, ctypes.c_void_p)),
    "glUniform3fv": (None, (ctypes.c_int, ctypes.c_int, ctypes.c_void_p)),
    "glUniform3f": (None, (ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float)),
    "glUniform2f": (None, (ctypes.c_int, ctypes.c_float, ctypes.c_float)),
    "glUniform1f": (None, (ctypes.c_int, ctypes.c_float)),
    "glUniform1i": (None, (ctypes.c_int, ctypes.c_int)),
    "glCreateShader": (ctypes.c_uint, (ctypes.c_uint,)),
    "glShaderSource": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)),
    "glCompileShader": (None, (ctypes.c_uint,)),
    "glGetShaderiv": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)),
    "glGetShaderInfoLog": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p)),
    "glCreateProgram": (ctypes.c_uint, ()),
    "glAttachShader": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glLinkProgram": (None, (ctypes.c_uint,)),
    "glGetProgramiv": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)),
    "glGetProgramInfoLog": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p)),
    "glDeleteShader": (None, (ctypes.c_uint,)),
    "glDrawArraysInstanced": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int)),
    "glDrawArrays": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_int)),
    "glGenFramebuffers": (None, (ctypes.c_int, ctypes.c_void_p)),
    "glBindFramebuffer": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glGenTextures": (None, (ctypes.c_int, ctypes.c_void_p)),
    "glBindTexture": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glTexImage2D": (None, (ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p)),
    "glTexParameteri": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_int)),
    "glFramebufferTexture2D": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                      ctypes.c_uint, ctypes.c_int)),
    "glGenRenderbuffers": (None, (ctypes.c_int, ctypes.c_void_p)),
    "glBindRenderbuffer": (None, (ctypes.c_uint, ctypes.c_uint)),
    "glRenderbufferStorage": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int)),
    "glFramebufferRenderbuffer": (None, (ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                         ctypes.c_uint)),
    "glCheckFramebufferStatus": (ctypes.c_uint, (ctypes.c_uint,)),
    "glReadPixels": (None, (ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)),
    "glPixelStorei": (None, (ctypes.c_uint, ctypes.c_int)),
    "glGetError": (ctypes.c_uint, ()),
}

GL = {}


def _load_gl(get_proc):
    for name, (restype, argtypes) in _FUNCS.items():
        addr = get_proc(name)
        if not addr:
            raise RuntimeError("missing GL entry: " + name)
        GL[name] = ctypes.CFUNCTYPE(restype, *argtypes)(addr)


def _gen1(gen):
    out = (ctypes.c_uint * 1)()
    gen(1, out)
    return out[0]


# ---------------- shaders ----------------
_SOLID_VERT = """#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNrm;
layout(location=2) in vec3 iPos;
layout(location=3) in float iScale;
layout(location=4) in vec3 iColor;
layout(location=5) in float iAlpha;
uniform mat4 uClip;
uniform float uZoom; uniform float uFocal;
out vec3 vN; out vec3 vC; out float vA;
void main(){
  vec4 cl = uClip * vec4(iPos, 1.0);
  float z2 = uFocal * (cl.w - 1.0);
  float sc = uZoom * uFocal / max(1.0, (uFocal + z2));
  vec3 wp = iPos + aPos * (iScale / sc);
  vN = aNrm; vC = iColor; vA = iAlpha;
  gl_Position = uClip * vec4(wp, 1.0);
}"""

_SOLID_FRAG = """#version 330 core
in vec3 vN; in vec3 vC; in float vA;
uniform vec3 uLight;
out vec4 oC;
void main(){
  vec3 N = normalize(vN);
  vec3 L = normalize(uLight);
  float dif = max(dot(N, L), 0.0);
  float hemi = 0.5 + 0.5 * N.y;
  vec3 col = vC * (0.30 + 0.25 * hemi + 0.95 * dif);
  oC = vec4(col, vA);
}"""

_BILL_VERT = """#version 330 core
layout(location=0) in vec3 aPos;
layout(location=2) in vec3 iPos;
layout(location=3) in float iScale;
layout(location=4) in vec3 iColor;
layout(location=5) in float iAlpha;
uniform mat4 uClip;
uniform float uZoom; uniform float uFocal; uniform vec2 uRes;
uniform vec3 uRight; uniform vec3 uUp;
uniform int uOrtho;
out vec3 vC; out float vA; out vec2 vUV;
void main(){
  vec4 cl;
  if (uOrtho == 1) {
    cl = uClip * vec4(iPos + vec3(aPos.xy * iScale, 0.0), 1.0);
  } else {
    vec4 c0 = uClip * vec4(iPos, 1.0);
    float z2 = uFocal * (c0.w - 1.0);
    float sc = uZoom * uFocal / max(1.0, (uFocal + z2));
    float wr = iScale / sc;
    vec3 off = (uRight * aPos.x + uUp * aPos.y) * wr;
    cl = uClip * vec4(iPos + off, 1.0);
  }
  vC = iColor; vA = iAlpha; vUV = aPos.xy;
  gl_Position = cl;
}"""

_FLAT_FRAG = """#version 330 core
in vec3 vC; in float vA; in vec2 vUV;
out vec4 oC;
void main(){ oC = vec4(vC * 0.95, vA); }"""

_GLOW_FRAG = """#version 330 core
in vec3 vC; in float vA; in vec2 vUV;
out vec4 oC;
void main(){
  float d = clamp(length(vUV), 0.0, 1.0);
  float a = (1.0 - d) * (1.0 - d) * vA * 0.45;
  oC = vec4(vC, a);
}"""

_LINE_VERT = """#version 330 core
layout(location=0) in vec3 aPos;
uniform mat4 uClip;
void main(){ gl_Position = uClip * vec4(aPos, 1.0); }"""

_LINE_FRAG = """#version 330 core
uniform vec3 uColor;
out vec4 oC;
void main(){ oC = vec4(uColor, 1.0); }"""


def _compile(vs_src, fs_src):
    def sh(kind, src):
        s = GL["glCreateShader"](kind)
        b = src.encode()
        arr = (ctypes.c_char_p * 1)(b)
        GL["glShaderSource"](s, 1, arr, None)
        GL["glCompileShader"](s)
        ok = (ctypes.c_int * 1)()
        GL["glGetShaderiv"](s, GL_COMPILE_STATUS, ok)
        if not ok[0]:
            buf = ctypes.create_string_buffer(2048)
            GL["glGetShaderInfoLog"](s, 2048, None, buf)
            raise RuntimeError("shader: " + buf.value.decode())
        return s

    v, f = sh(GL_VERTEX_SHADER, vs_src), sh(GL_FRAGMENT_SHADER, fs_src)
    p = GL["glCreateProgram"]()
    GL["glAttachShader"](p, v)
    GL["glAttachShader"](p, f)
    GL["glLinkProgram"](p)
    ok = (ctypes.c_int * 1)()
    GL["glGetProgramiv"](p, GL_LINK_STATUS, ok)
    if not ok[0]:
        buf = ctypes.create_string_buffer(2048)
        GL["glGetProgramInfoLog"](p, 2048, None, buf)
        raise RuntimeError("link: " + buf.value.decode())
    GL["glDeleteShader"](v)
    GL["glDeleteShader"](f)
    return p


# ---------------- geometry (pos3+nrm3, non-indexed) ----------------
def _flat_normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / n, ny / n, nz / n)


def _build_tris(faces):
    pos, nrm = [], []
    for tri in faces:
        n = _flat_normal(*tri)
        for p in tri:
            pos += list(p)
            nrm += list(n)
    return pos, nrm


def _sphere(r=0.9, ws=12, hs=8):
    faces = []
    for iy in range(hs):
        p0, p1 = math.pi * iy / hs, math.pi * (iy + 1) / hs
        for ix in range(ws):
            a0, a1 = 2 * math.pi * ix / ws, 2 * math.pi * (ix + 1) / ws
            q = lambda p, a: (r * math.sin(p) * math.cos(a), r * math.cos(p), r * math.sin(p) * math.sin(a))
            faces.append((q(p0, a0), q(p1, a0), q(p1, a1)))
            faces.append((q(p0, a0), q(p1, a1), q(p0, a1)))
    return _build_tris(faces)


def _cube(h=0.7):
    c = [(-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
         (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)]
    quads = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7),
             (1, 5, 6, 2), (4, 5, 1, 0), (3, 2, 6, 7)]
    faces = []
    for a, b, d, e in quads:
        faces.append((c[a], c[b], c[d]))
        faces.append((c[a], c[d], c[e]))
    # outward faces need CCW winding seen from outside; fix by normal check
    fixed = []
    for tri in faces:
        n = _flat_normal(*tri)
        cx = sum(p[0] for p in tri) / 3
        cy = sum(p[1] for p in tri) / 3
        cz = sum(p[2] for p in tri) / 3
        if n[0] * cx + n[1] * cy + n[2] * cz < 0:
            tri = (tri[0], tri[2], tri[1])
        fixed.append(tri)
    return _build_tris(fixed)


def _pyramid(r=0.95, h=1.7):
    apex = (0, h / 2, 0)
    ring = [(r * math.cos(math.pi / 4 + i * math.pi / 2), -h / 2,
             r * math.sin(math.pi / 4 + i * math.pi / 2)) for i in range(4)]
    faces = [(apex, ring[i], ring[(i + 1) % 4]) for i in range(4)]
    faces += [(ring[0], ring[2], ring[1]), (ring[0], ring[3], ring[2])]
    return _build_tris(faces)


def _torus(R=0.65, r=0.30, ws=20, hs=10):
    faces = []
    for iy in range(hs):
        for ix in range(ws):
            u0, u1 = 2 * math.pi * ix / ws, 2 * math.pi * (ix + 1) / ws
            v0, v1 = 2 * math.pi * iy / hs, 2 * math.pi * (iy + 1) / hs
            q = lambda u, v: ((R + r * math.cos(v)) * math.cos(u),
                              r * math.sin(v),
                              (R + r * math.cos(v)) * math.sin(u))
            faces.append((q(u0, v0), q(u1, v0), q(u1, v1)))
            faces.append((q(u0, v0), q(u1, v1), q(u0, v1)))
    return _build_tris(faces)


def _octa(r=1.0):
    t, b = (0, r, 0), (0, -r, 0)
    ring = [(r, 0, 0), (0, 0, r), (-r, 0, 0), (0, 0, -r)]
    faces = []
    for i in range(4):
        faces.append((t, ring[i], ring[(i + 1) % 4]))
        faces.append((b, ring[(i + 1) % 4], ring[i]))
    return _build_tris(faces)


def _flat(pts2):
    """Fan around centroid, y-DOWN canvas convention; normal +z."""
    cx = sum(p[0] for p in pts2) / len(pts2)
    cy = sum(p[1] for p in pts2) / len(pts2)
    pos, nrm = [], []
    for i in range(len(pts2)):
        a, b = pts2[i], pts2[(i + 1) % len(pts2)]
        for p in ((cx, cy), a, b):
            pos += [p[0], p[1], 0.0]
            nrm += [0.0, 0.0, 1.0]
    return pos, nrm


def _star2(outer=1.0, inner=0.45):
    pts = []
    for k in range(10):
        a = (k / 10) * math.pi * 2 - math.pi / 2
        rr = outer if k % 2 == 0 else inner
        pts.append((math.cos(a) * rr, math.sin(a) * rr))
    return _flat(pts)


def _frame2(half=1.0, th=0.18):
    o, t = half, th
    quads = [((-o, -o), (o, -o), (o, -o + t), (-o, -o + t)),
             ((-o, o - t), (o, o - t), (o, o), (-o, o)),
             ((-o, -o + t), (-o + t, -o + t), (-o + t, o - t), (-o, o - t)),
             ((o - t, -o + t), (o, -o + t), (o, o - t), (o - t, o - t))]
    pos, nrm = [], []
    for q in quads:
        for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            for p in tri:
                pos += [p[0], p[1], 0.0]
                nrm += [0.0, 0.0, 1.0]
    return pos, nrm


def _geo_dict():
    tri = [(0, -1.2), (1.1, 0.9), (-1.1, 0.9)]
    dia = [(0, -1), (0.7, 0), (0, 1), (-0.7, 0)]
    sq = [(-0.9, -0.9), (0.9, -0.9), (0.9, 0.9), (-0.9, 0.9)]
    circ = [(math.cos(i / 28 * math.pi * 2), math.sin(i / 28 * math.pi * 2))
            for i in range(28)]
    return {
        "sphere": _sphere(), "cube": _cube(), "pyramid": _pyramid(),
        "torus": _torus(), "diamond": _octa(),
        "square": _flat(sq), "billboard": _flat(sq),
        "triangle": _flat(tri), "star": _star2(), "diamond2d": _flat(dia),
        "line": _flat([(-1.6, -0.25), (1.6, -0.25), (1.6, 0.25), (-1.6, 0.25)]),
        "circle": _flat(circ), "custom": _frame2(),
    }


# ---------------- matrices ----------------
def mat_clip_3d(yaw, pitch, zoom, focal, W, H, vcx, vcy, ox, oy):
    """Column-major 4x4 mapping world -> clip, EXACTLY matching
    StudioApp._proj screen coords (verified numerically in test_gl)."""
    syaw, cyaw = math.sin(yaw), math.cos(yaw)
    spit, cpit = math.sin(pitch), math.cos(pitch)
    A = 2.0 * zoom / W
    B = 2.0 * zoom / H
    Ox = vcx + ox - W / 2.0
    Oy = vcy + oy - H / 2.0
    f = max(1.0, focal)
    # rows: x1=(cy,0,sy), y2=(sp*sy,cp,-sp*cy), w=(−sy*cp,f... )/f;
    # clip.x = A*x1 + (2Ox/W)*w ; clip.y = B*y2 − (2Oy/H)*w  (folded per column)
    kx, ky = 2.0 * Ox / W, -2.0 * Oy / H
    x1 = (cyaw, 0.0, syaw)
    y2 = (spit * syaw, cpit, -spit * cyaw)
    wr = (-syaw * cpit / f, spit / f, cpit * cyaw / f)
    return [A * x1[0] + kx * wr[0], B * y2[0] + ky * wr[0], 0.0, wr[0],
            A * x1[1] + kx * wr[1], B * y2[1] + ky * wr[1], 0.0, wr[1],
            A * x1[2] + kx * wr[2], B * y2[2] + ky * wr[2], 0.0, wr[2],
            kx * 1.0, ky * 1.0, 0.0, 1.0]


def orbit_right_up(yaw, pitch):
    syaw, cyaw = math.sin(yaw), math.cos(yaw)
    spit, cpit = math.sin(pitch), math.cos(pitch)
    return (cyaw, 0.0, syaw), (spit * syaw, cpit, -spit * cyaw)


def subrect_clip(m, W, H, x0, y0, w2, h2):
    """Remap a full-canvas clip matrix into a canvas subrect (x0,y0 top-down).
    Pixels land 1:1 with the full-frame mapping (verified in test_clip)."""
    sx, sy = W / w2, H / h2
    tx = (W - 2.0 * x0) / w2 - 1.0
    ty = (2.0 * y0 - (H - h2)) / h2
    o = list(m)
    for j in range(4):
        wrow = m[j * 4 + 3]
        o[j * 4 + 0] = sx * m[j * 4 + 0] + tx * wrow
        o[j * 4 + 1] = sy * m[j * 4 + 1] + ty * wrow
    return o


def mat_ortho(l, r, t, b, n, f):
    return [2 / (r - l), 0, 0, 0, 0, 2 / (t - b), 0, 0, 0, 0,
            -2 / (f - n), 0, -(r + l) / (r - l), -(t + b) / (t - b),
            -(f + n) / (f - n), 1]


# ---------------- renderer ----------------
SOLIDS = ("sphere", "cube", "pyramid", "torus", "diamond")


# Blend mode table (effect blendingMode -> GL factors + equation).
# Matches the extension/preview fallbacks: Overlay has no GL fixed-function
# equivalent and degrades to Normal; unknown modes degrade to Normal.
BLEND_MAP = {
    "Normal": (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_FUNC_ADD),
    "Additive": (GL_SRC_ALPHA, GL_ONE, GL_FUNC_ADD),
    "Screen": (GL_ONE, GL_ONE_MINUS_SRC_COLOR, GL_FUNC_ADD),
    "Multiply": (GL_DST_COLOR, GL_ONE_MINUS_SRC_ALPHA, GL_FUNC_ADD),
    "Subtractive": (GL_ONE, GL_ONE, GL_FUNC_REVERSE_SUBTRACT),
    "Lighten": (GL_ONE, GL_ONE, GL_MAX),
}


class GLView:
    """Offscreen GPU renderer. .ok False => caller uses canvas items."""

    def __init__(self):
        self.ok = False
        self.win = None
        self.fbo = self.tex = self.rb = 0
        self.fw = self.fh = 0
        try:
            self._init()
            self.ok = True
        except Exception:
            self.ok = False

    def _init(self):
        import glfw
        if not glfw.init():
            raise RuntimeError("glfw.init failed")
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        self._glfw = glfw
        self.win = glfw.create_window(16, 16, "glview", None, None)
        if not self.win:
            raise RuntimeError("hidden GL window failed")
        glfw.make_context_current(self.win)
        _load_gl(glfw.get_proc_address)
        GL["glPixelStorei"](GL_PACK_ALIGNMENT, 1)
        GL["glDisable"](0x0B71)  # DEPTH_TEST: additive order-free
        GL["glDepthMask"](GL_FALSE)
        GL["glEnable"](GL_BLEND)
        self._blend = None
        self.set_blend("Additive")  # historic default; render() overrides per call
        self.p_solid = _compile(_SOLID_VERT, _SOLID_FRAG)
        self.p_flat = _compile(_BILL_VERT, _FLAT_FRAG)
        self.p_glow = _compile(_BILL_VERT, _GLOW_FRAG)
        self.p_line = _compile(_LINE_VERT, _LINE_FRAG)
        self.vaos = {}
        for name, (pos, nrm) in _geo_dict().items():
            vao = _gen1(GL["glGenVertexArrays"])
            GL["glBindVertexArray"](vao)
            vb = _gen1(GL["glGenBuffers"])
            GL["glBindBuffer"](GL_ARRAY_BUFFER, vb)
            inter = array("f")
            for i in range(0, len(pos), 3):
                inter.extend([pos[i], pos[i + 1], pos[i + 2],
                              nrm[i], nrm[i + 1], nrm[i + 2]])
            blob = inter.tobytes()
            GL["glBufferData"](GL_ARRAY_BUFFER, len(blob), blob, GL_STATIC_DRAW)
            GL["glVertexAttribPointer"](0, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(0))
            GL["glEnableVertexAttribArray"](0)
            GL["glVertexAttribPointer"](1, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(12))
            GL["glEnableVertexAttribArray"](1)
            self.vaos[name] = (vao, len(pos) // 3, vb)
        # shared glow quad (-1..1)
        vao = _gen1(GL["glGenVertexArrays"])
        GL["glBindVertexArray"](vao)
        vb = _gen1(GL["glGenBuffers"])
        GL["glBindBuffer"](GL_ARRAY_BUFFER, vb)
        q = array("f", [-1, -1, 0, 0, 0, 1, 1, -1, 0, 0, 0, 1,
                        1, -1, 0, 0, 0, 1, -1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1])
        blob = q.tobytes()
        GL["glBufferData"](GL_ARRAY_BUFFER, len(blob), blob, GL_STATIC_DRAW)
        GL["glVertexAttribPointer"](0, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(0))
        GL["glEnableVertexAttribArray"](0)
        GL["glVertexAttribPointer"](1, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(12))
        GL["glEnableVertexAttribArray"](1)
        self.vao_quad = vao
        # dynamic instance + line buffers
        self.inst = _gen1(GL["glGenBuffers"])
        self.line_vbo = _gen1(GL["glGenBuffers"])
        self.line_vao = _gen1(GL["glGenVertexArrays"])
        ll = 1.0 / math.sqrt(0.35 ** 2 + 0.8 ** 2 + 0.45 ** 2)
        self.light = (0.35 * ll, 0.8 * ll, 0.45 * ll)

    def _uloc(self, prog, name):
        return GL["glGetUniformLocation"](prog, name.encode())

    def _mat4(self, prog, name, m):
        loc = self._uloc(prog, name)
        if loc >= 0:
            GL["glUniformMatrix4fv"](loc, 1, GL_FALSE, (ctypes.c_float * 16)(*m))

    def _set_clip(self, prog, clip, zoom, focal, res, right, up, ortho):
        GL["glUseProgram"](prog)
        self._mat4(prog, "uClip", clip)
        for nm, val in (("uZoom", zoom), ("uFocal", focal)):
            loc = self._uloc(prog, nm)
            if loc >= 0:
                GL["glUniform1f"](loc, val)
        loc = self._uloc(prog, "uRes")
        if loc >= 0:
            GL["glUniform2f"](loc, res[0], res[1])
        # NOTE: uRes declared vec2; 3fv over-supplies -> use 2f path instead
        loc = self._uloc(prog, "uRight")
        if loc >= 0 and right is not None:
            GL["glUniform3fv"](loc, 1, (ctypes.c_float * 3)(*right))
        loc = self._uloc(prog, "uUp")
        if loc >= 0 and up is not None:
            GL["glUniform3fv"](loc, 1, (ctypes.c_float * 3)(*up))
        loc = self._uloc(prog, "uOrtho")
        if loc >= 0:
            GL["glUniform1i"](loc, ortho)
        loc = self._uloc(prog, "uLight")
        if loc >= 0:
            GL["glUniform3fv"](loc, 1, (ctypes.c_float * 3)(*self.light))

    def _upload_instances(self, vao, items, smul=1.0):
        """items: list of (x,y,z,scale,r,g,b,a)."""
        GL["glBindVertexArray"](vao)
        GL["glBindBuffer"](GL_ARRAY_BUFFER, self.inst)
        if smul == 1.0:
            blob = array("f", [v for it in items for v in it]).tobytes()
        else:
            flat = []
            for it in items:
                flat += [it[0], it[1], it[2], it[3] * smul,
                         it[4], it[5], it[6], it[7]]
            blob = array("f", flat).tobytes()
        GL["glBufferData"](GL_ARRAY_BUFFER, len(blob) if blob else 1,
                           blob if blob else None, GL_DYNAMIC_DRAW)
        stride = 32
        for loc, size, off in ((2, 3, 0), (3, 1, 12), (4, 3, 16), (5, 1, 28)):
            GL["glVertexAttribPointer"](loc, size, GL_FLOAT, GL_FALSE, stride,
                                        ctypes.c_void_p(off))
            GL["glEnableVertexAttribArray"](loc)
            GL["glVertexAttribDivisor"](loc, 1)
        return len(items)

    def _draw_lines(self, segs, rgb, clip):
        """segs: flat [x1,y1,z1,x2,y2,z2,...]. One color."""
        if not segs:
            return
        GL["glUseProgram"](self.p_line)
        self._mat4(self.p_line, "uClip", clip)
        loc = self._uloc(self.p_line, "uColor")
        if loc >= 0:
            GL["glUniform3f"](loc, rgb[0], rgb[1], rgb[2])
        GL["glBindVertexArray"](self.line_vao)
        GL["glBindBuffer"](GL_ARRAY_BUFFER, self.line_vbo)
        blob = array("f", segs).tobytes()
        GL["glBufferData"](GL_ARRAY_BUFFER, len(blob), blob, GL_DYNAMIC_DRAW)
        GL["glVertexAttribPointer"](0, 3, GL_FLOAT, GL_FALSE, 12, ctypes.c_void_p(0))
        GL["glEnableVertexAttribArray"](0)
        GL["glVertexAttribDivisor"](0, 0)
        GL["glDrawArrays"](GL_LINES, 0, len(segs) // 3)

    def _ensure_fbo(self, w, h):
        if w == self.fw and h == self.fh and self.fbo:
            return
        self.fw, self.fh = w, h
        if not self.fbo:
            self.fbo = _gen1(GL["glGenFramebuffers"])
            self.tex = _gen1(GL["glGenTextures"])
            self.rb = _gen1(GL["glGenRenderbuffers"])
        GL["glBindTexture"](GL_TEXTURE_2D, self.tex)
        GL["glTexImage2D"](GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA,
                           GL_UNSIGNED_BYTE, None)
        GL["glTexParameteri"](GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        GL["glTexParameteri"](GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        GL["glBindRenderbuffer"](GL_RENDERBUFFER, self.rb)
        GL["glRenderbufferStorage"](GL_RENDERBUFFER, GL_DEPTH_COMPONENT16, w, h)
        GL["glBindFramebuffer"](GL_FRAMEBUFFER, self.fbo)
        GL["glFramebufferTexture2D"](GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                     GL_TEXTURE_2D, self.tex, 0)
        GL["glFramebufferRenderbuffer"](GL_FRAMEBUFFER, GL_DEPTH_COMPONENT16,
                                        GL_RENDERBUFFER, self.rb)
        if GL["glCheckFramebufferStatus"](GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("FBO incomplete")

    def set_blend(self, mode):
        """Apply an effect blendingMode to the GL state.

        Unknown/unsupported modes (e.g. Overlay) degrade to Normal.
        Returns the canonical mode actually applied.
        """
        key = mode if mode in BLEND_MAP else "Normal"
        src, dst, eq = BLEND_MAP[key]
        GL["glBlendFunc"](src, dst)
        GL["glBlendEquation"](eq)
        self._blend = key
        return key

    def render(self, buckets, glow_items, W, H, *, ortho, clip, zoom, focal,
               right=None, up=None, bg=(0.08, 0.08, 0.10), grid=(), vp=None,
               blend="Additive"):
        """buckets: {shape: [(x,y,z,s,r,g,b,a)...]} (world or px coords).
        grid: [(segments_xyz, (r,g,b)), ...]. vp: optional (x0,y0,w2,h2)
        canvas-coords subrect (dirty-region rendering). Returns raw PPM bytes."""
        if vp is None:
            x0g, y0g, w2, h2 = 0, 0, max(1, int(W)), max(1, int(H))
            clip2 = clip
        else:
            x0, y0, w2, h2 = (max(0, int(v)) for v in (vp[0], vp[1], max(1, vp[2]), max(1, vp[3])))
            clip2 = subrect_clip(clip, W, H, x0, y0, w2, h2)
            x0g, y0g = x0, H - y0 - h2
        w, h = max(1, int(w2)), max(1, int(h2))
        self._ensure_fbo(max(1, int(W)), max(1, int(H)))  # full canvas FBO
        GL["glBindFramebuffer"](GL_FRAMEBUFFER, self.fbo)
        self.set_blend(blend)
        GL["glViewport"](x0g, y0g, w, h)
        GL["glClearColor"](bg[0], bg[1], bg[2], 1.0)
        GL["glClear"](GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        res = (float(w), float(h))
        for segs, rgb in grid:
            self._draw_lines(segs, rgb, clip2)
        for prog, is_glow in ((self.p_solid, False), (self.p_flat, False),
                              (self.p_glow, True)):
            self._set_clip(prog, clip2, zoom, focal, res, right, up, ortho)
            if is_glow:
                n = self._upload_instances(self.vao_quad, glow_items, smul=2.4)
                if n:
                    GL["glDrawArraysInstanced"](GL_TRIANGLES, 0, 6, n)
                continue
            for shape, items in buckets.items():
                if not items:
                    continue
                want_solid = (shape in SOLIDS) and not ortho
                if want_solid != (prog == self.p_solid):
                    continue
                # 2D "diamond" is the flat kite; 3D "diamond" is the octahedron
                key = "diamond2d" if (shape == "diamond" and ortho) else shape
                if key not in self.vaos:
                    continue
                vao, count, _vb = self.vaos[key]
                n = self._upload_instances(vao, items)
                GL["glDrawArraysInstanced"](GL_TRIANGLES, 0, count, n)
        buf = ctypes.create_string_buffer(w * h * 3)
        GL["glReadPixels"](x0g, y0g, w, h, GL_RGB, GL_UNSIGNED_BYTE, buf)
        mv = memoryview(buf)
        stride = w * 3
        out = b"".join(mv[(h - 1 - y) * stride:(h - y) * stride] for y in range(h))
        head = ("P6\n%d %d\n255\n" % (w, h)).encode()
        return bytes(head + out)

    def close(self):
        try:
            if self.win:
                self._glfw.destroy_window(self.win)
                self._glfw.terminate()
        except Exception:
            pass
        self.ok = False
