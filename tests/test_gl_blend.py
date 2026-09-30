# Pixel-level GL blend test: one known source dot over a known backdrop must
# match the analytic formula of each mode (tolerance covers byte rounding).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from render.gl_view import GLView, mat_ortho

v = GLView()
assert v.ok, "GL init failed"

# set_blend mapping + fallbacks (no GL draw needed)
assert v.set_blend("Normal") == "Normal"
assert v.set_blend("Additive") == "Additive"
assert v.set_blend("Screen") == "Screen"
assert v.set_blend("Multiply") == "Multiply"
assert v.set_blend("Subtractive") == "Subtractive"
assert v.set_blend("Lighten") == "Lighten"
assert v.set_blend("Overlay") == "Normal"
assert v.set_blend("Bogus") == "Normal"
print("set_blend mapping: OK")

W = H = 200
CX, CY = 100.0, 100.0
# flat-shader source: rgb * 0.95, alpha as given
SR, SG, SB, A = 1.0, 0.5, 0.25, 0.6
S = (SR * 0.95, SG * 0.95, SB * 0.95)
BG = (0.2, 0.35, 0.5)
buckets = {"circle": [(CX, CY, 0.0, 60.0, SR, SG, SB, A)]}
clip = mat_ortho(0, W, 0, H, -1000, 1000)


def center(px_ppm):
    head_end = px_ppm.index(b"\n255\n") + 5
    dims = px_ppm[:head_end].split()
    w, h = int(dims[1]), int(dims[2])
    raw = px_ppm[head_end:]
    # PPM row 0 = top (verified in test_imgui_raster)
    x, y = 100, 100
    o = (y * w + x) * 3
    return raw[o] / 255.0, raw[o + 1] / 255.0, raw[o + 2] / 255.0


def close(got, want, mode, tol=0.035):
    bad = [abs(a - b) for a, b in zip(got, want)]
    assert all(d <= tol for d in bad), (mode, got, want, bad)


def expect(mode):
    s, d, a = S, BG, A
    if mode == "Normal":
        return tuple(x * a + y * (1 - a) for x, y in zip(s, d))
    if mode == "Additive":
        return tuple(x * a + y for x, y in zip(s, d))
    if mode == "Screen":
        return tuple(x + y * (1 - x) for x, y in zip(s, d))
    if mode == "Multiply":
        return tuple(x * y + y * (1 - a) for x, y in zip(s, d))
    if mode == "Subtractive":
        return tuple(max(y - x, 0.0) for x, y in zip(s, d))
    if mode == "Lighten":
        return tuple(max(x, y) for x, y in zip(s, d))
    raise AssertionError(mode)


for mode in ("Normal", "Additive", "Screen", "Multiply", "Subtractive", "Lighten"):
    ppm = v.render(buckets, [], W, H, ortho=1, clip=clip, zoom=1.0,
                   focal=620.0, bg=BG, grid=(), blend=mode)
    close(center(ppm), expect(mode), mode)
    print(f"{mode}: OK")

# fallbacks render exactly like Normal
ref = v.render(buckets, [], W, H, ortho=1, clip=clip, zoom=1.0,
               focal=620.0, bg=BG, grid=(), blend="Normal")
for mode in ("Overlay", "Bogus"):
    alt = v.render(buckets, [], W, H, ortho=1, clip=clip, zoom=1.0,
                   focal=620.0, bg=BG, grid=(), blend=mode)
    assert alt == ref, mode
print("fallbacks == Normal: OK")

# backdrop untouched far from the dot
raw = ref[ref.index(b"\n255\n") + 5:]
o = (10 * W + 10) * 3
got = (raw[o] / 255.0, raw[o + 1] / 255.0, raw[o + 2] / 255.0)
close(got, BG, "backdrop", tol=0.02)
print("backdrop intact: OK")
v.close()
print("GL-BLEND-OK")
