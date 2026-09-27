# -*- coding: utf-8 -*-
from render.gl_view import GLView, mat_clip_3d, mat_ortho

v = GLView()
assert v.ok, "GL init failed"
print("GL init OK")

IDENT = None
# 2D: orange core + blue + star (pixel space)
buckets = {"circle": [(400.0, 300.0, 0.0, 14.0, 1.0, 0.5, 0.0, 1.0),
                      (200.0, 150.0, 0.0, 8.0, 0.2, 0.6, 1.0, 0.8)],
           "star": [(600.0, 450.0, 0.0, 12.0, 1.0, 1.0, 0.3, 1.0)]}
glow = [t for items in buckets.values() for t in items]
png = v.render(buckets, glow, 800, 600, ortho=1,
                   clip=mat_ortho(0, 800, 0, 600, -1000, 1000),
                   zoom=1.0, focal=620.0, bg=(0.08, 0.08, 0.10), grid=())
assert png[:15] == b"P6\n800 600\n255\n", png[:20]
assert len(png) > 10000, len(png)
print(f"2D render OK ({len(png)} bytes)")

# 3D: lit sphere + cube + billboard star + grid
b3 = {"sphere": [(0.0, 0.0, 0.0, 14.0, 1.0, 0.55, 0.05, 1.0),
                 (60.0, 20.0, -30.0, 10.0, 1.0, 0.8, 0.2, 0.9)],
      "cube": [(50.0, 30.0, 20.0, 12.0, 0.25, 0.55, 1.0, 1.0)],
      "star": [(0.0, 0.0, 0.0, 8.0, 1.0, 1.0, 1.0, 1.0)]}
g3 = [t for items in b3.values() for t in items]
grid = [([-260.0, 0.0, 0.0, 260.0, 0.0, 0.0], (0.17, 0.18, 0.27))]
clip = mat_clip_3d(0.7, 0.42, 1.0, 620.0, 800, 600, 400, 312, 0, 0)
from render.gl_view import orbit_right_up
ru, uu = orbit_right_up(0.7, 0.42)
png3 = v.render(b3, g3, 800, 600, ortho=0, clip=clip, zoom=1.0,
                focal=620.0, right=ru, up=uu, bg=(0.08, 0.08, 0.10),
                grid=grid)
assert png3[:15] == b"P6\n800 600\n255\n"
assert len(png3) > 10000, len(png3)
print(f"3D render OK ({len(png3)} bytes)")
v.close()
print("GL_RENDER OK")
