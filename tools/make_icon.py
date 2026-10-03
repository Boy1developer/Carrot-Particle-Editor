# -*- coding: utf-8 -*-
"""Build the Lempo app icons from icon.jpg (repo-root brand artwork).

- Square center-crop -> 1024, soft rounded corners (26% radius, 4x
  supersampled mask + 1.5px feather for a smooth edge).
- assets/app_icon.png  : window + chooser logo.
- assets/app_icon.ico  : multi-size ICO wired into packaging/LempoParticleEditor.spec
  (exe file/taskbar icon) and the desktop shortcut.
Usage: python tools/make_icon.py (run from the repo root)
Requires: pillow
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icon.jpg")
ICON_SIZE = 1024
CORNER_R = 0.26  # fraction of side
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]


def rounded_mark(src, size=ICON_SIZE):
    w, h = src.size
    s = min(w, h)
    mark = src.crop(((w - s) // 2, (h - s) // 2,
                     (w - s) // 2 + s, (h - s) // 2 + s))
    mark = mark.resize((size, size), Image.LANCZOS)
    ss = 4
    m = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size * ss - 1, size * ss - 1],
        radius=int(size * CORNER_R * ss), fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    m = m.filter(ImageFilter.GaussianBlur(1.5))
    mark = mark.convert("RGBA")
    mark.putalpha(m)
    return mark


def main():
    src = Image.open(SRC).convert("RGB")
    print("src:", src.size, src.mode)
    mark = rounded_mark(src)
    png_path = os.path.join(ROOT, "assets", "app_icon.png")
    ico_path = os.path.join(ROOT, "assets", "app_icon.ico")
    mark.save(png_path)
    mark.save(ico_path, sizes=ICO_SIZES)
    print("wrote", png_path, mark.size)
    print("wrote", ico_path,
          f"{os.path.getsize(ico_path) / 1024:.0f} KB", [s_[0] for s_ in ICO_SIZES])


if __name__ == "__main__":
    main()
