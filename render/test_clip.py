# -*- coding: utf-8 -*-
import math
import random
from render.gl_view import mat_clip_3d


def proj_ref(x, y, z, yaw, pitch, zoom, ox, oy, focal, vcx, vcy):
    """Copied math from StudioApp._proj."""
    syaw, cyaw = math.sin(yaw), math.cos(yaw)
    spit, cpit = math.sin(pitch), math.cos(pitch)
    x1 = x * cyaw + z * syaw
    z1 = -x * syaw + z * cyaw
    y2 = y * cpit - z1 * spit
    z2 = y * spit + z1 * cpit
    scale = zoom * focal / (focal + z2)
    return (vcx + ox + x1 * scale, vcy + oy - y2 * scale)


def apply_clip(m, x, y, z):
    cx = m[0] * x + m[4] * y + m[8] * z + m[12]
    cy = m[1] * x + m[5] * y + m[9] * z + m[13]
    cw = m[3] * x + m[7] * y + m[11] * z + m[15]
    return cx / cw, cy / cw


random.seed(3)
bad = 0
for _ in range(300):
    yaw = random.uniform(-3.14, 3.14)
    pitch = random.uniform(-1.3, 1.3)
    zoom = random.uniform(0.3, 4.0)
    ox, oy = random.uniform(-200, 200), random.uniform(-200, 200)
    fov = random.uniform(20, 110)
    focal = 300 / max(0.05, math.tan(math.radians(fov / 2)))
    W, H = 1280, 800
    vcx, vcy = W * 0.5, H * 0.52
    m = mat_clip_3d(yaw, pitch, zoom, focal, W, H, vcx, vcy, ox, oy)
    for _ in range(10):
        x, y, z = (random.uniform(-260, 260) for _ in range(3))
        sx, sy = proj_ref(x, y, z, yaw, pitch, zoom, ox, oy, focal, vcx, vcy)
        nx, ny = apply_clip(m, x, y, z)
        ex = (sx - W / 2) / (W / 2)
        ey = -(sy - H / 2) / (H / 2)
        if abs(nx - ex) > 1e-9 or abs(ny - ey) > 1e-9:
            bad += 1
            if bad < 4:
                print("MISMATCH", (nx, ny), (ex, ey))
print("clip vs _proj mismatches:", bad, "/3000")
assert bad == 0
print("CLIP_PARITY OK")
