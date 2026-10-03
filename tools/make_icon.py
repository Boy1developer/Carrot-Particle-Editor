# -*- coding: utf-8 -*-
"""Build the Lempo app icons from icon.jpg (repo-root brand artwork).

- assets/app_icon.png  : square 1024 mark (window + chooser logo).
- assets/app_icon.ico  : multi-size ICO wired into packaging/LempoParticleEditor.spec
  (exe file/taskbar icon) and the desktop shortcut.
Usage: python tools/make_icon.py (run from the repo root)
Requires: pillow
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icon.jpg")
ICON_SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]


def main():
    src = Image.open(SRC).convert("RGB")
    print("src:", src.size, src.mode)
    w, h = src.size
    s = min(w, h)
    mark = src.crop(((w - s) // 2, (h - s) // 2,
                     (w - s) // 2 + s, (h - s) // 2 + s))
    mark = mark.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    png_path = os.path.join(ROOT, "assets", "app_icon.png")
    ico_path = os.path.join(ROOT, "assets", "app_icon.ico")
    mark.save(png_path)
    mark.save(ico_path, sizes=ICO_SIZES)
    print("wrote", png_path, mark.size)
    print("wrote", ico_path,
          f"{os.path.getsize(ico_path) / 1024:.0f} KB", [s_[0] for s_ in ICO_SIZES])


if __name__ == "__main__":
    main()
