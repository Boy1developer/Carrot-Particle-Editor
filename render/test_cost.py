# -*- coding: utf-8 -*-
import random
import time
import tkinter as tk
from render.gl_view import GLView, mat_clip_3d, orbit_right_up

v = GLView()
assert v.ok
random.seed(5)
W, H = 970, 821
N = 20
items = [(random.uniform(0, 260), random.uniform(0, 260), random.uniform(-100, 100),
          random.uniform(4, 12),
          random.random(), random.random(), random.random(),
          random.uniform(0.4, 1.0)) for _ in range(N)]
buckets = {"sphere": items}
ru, uu = orbit_right_up(0.7, 0.42)
clip = mat_clip_3d(0.7, 0.42, 1.0, 620.0, W, H, W / 2, H * 0.52, 0, 0)
grid = [([-260.0, 0.0, -260.0, 260.0, 0.0, -260.0,
          -260.0, 0.0, 260.0, 260.0, 0.0, 260.0,
          0.0, 0.0, -260.0, 0.0, 0.0, 260.0,
          0.0, 0.0, 260.0, 0.0, 0.0, -260.0], (0.17, 0.18, 0.27))]
png = v.render(buckets, items, W, H, ortho=0, clip=clip, zoom=1.0,
               focal=620.0, right=ru, up=uu, bg=(0.08, 0.08, 0.11), grid=grid)

# quantize a copy to 4-bit/channel
head_end = png.index(b'\n255\n') + 5
raw = bytearray(png[head_end:])
for i in range(0, len(raw), 3):
    raw[i] &= 0xF0
    raw[i + 1] &= 0xF0
    raw[i + 2] &= 0xF0
png_q = bytes(png[:head_end]) + bytes(raw)

root = tk.Tk()
root.withdraw()
ph = tk.PhotoImage()
K = 6
for _ in range(2):
    ph.configure(data=png, format="ppm")
t = time.perf_counter()
for _ in range(K):
    ph.configure(data=png, format="ppm")
print(f"raw colors: {(time.perf_counter()-t)/K*1000:.0f} ms")
t = time.perf_counter()
for _ in range(K):
    ph.configure(data=png_q, format="ppm")
print(f"quantized 4-bit: {(time.perf_counter()-t)/K*1000:.0f} ms")
v.close()
root.destroy()
