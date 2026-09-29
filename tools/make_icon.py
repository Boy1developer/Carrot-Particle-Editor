# -*- coding: utf-8 -*-
"""Build transparent Explorer icon from assets/download.png (white background art).

- Keys out the white background (border flood-fill, tolerance + edge feather).
- assets/logo_full.png : whole logo (card + text), transparent.
- assets/app_icon.png  : square 1024 artwork-only mark (no text, icon-legible).
- assets/app_icon.ico  : multi-size ICO wired into packaging/CarrotParticleEditor.spec.
Usage: python tools/make_icon.py (run from the repo root)
Requires: pillow
"""
import os
from collections import deque

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "download.png")
ART_BOTTOM = 790  # white gap row between card artwork and CARROT text
BG = 245  # min-channel threshold for background candidates
ICON_SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]


def key_white(im):
    """Return RGBA copy with border-connected near-white turned transparent."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    seen = bytearray(w * h)
    dq = deque()

    def push(x, y):
        if 0 <= x < w and 0 <= y < h and not seen[y * w + x]:
            if min(px[x, y]) >= BG:
                seen[y * w + x] = 1
                dq.append((x, y))

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)
    while dq:
        x, y = dq.popleft()
        push(x + 1, y)
        push(x - 1, y)
        push(x, y + 1)
        push(x, y - 1)

    # Text band (below the artwork gap): every near-white pixel is
    # background, including enclosed letter counters the flood fill
    # cannot reach. The card artwork above keeps flood-fill only so
    # bubble/sparkle highlights survive.
    for y in range(ART_BOTTOM + 10, h):
        for x in range(w):
            if not seen[y * w + x] and min(px[x, y]) >= BG:
                seen[y * w + x] = 1

    alpha = Image.frombytes("L", (w, h), bytes(seen))
    alpha = alpha.point(lambda v: 0 if v else 255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def square_mark(art):
    bbox = art.getbbox()
    if not bbox:
        raise SystemExit("ABORT: no foreground found after keying.")
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    side = max(w, h)
    pad = int(side * 0.05)
    side += pad * 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(art.crop(bbox), ((side - w) // 2, (side - h) // 2), art.crop(bbox))
    return canvas.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def main():
    src = Image.open(SRC)
    print("src:", src.size, src.mode)

    full = key_white(src)
    full_path = os.path.join(ROOT, "assets", "logo_full.png")
    full.save(full_path)
    print("wrote", full_path, full.size)

    art = full.crop((0, 0, full.width, ART_BOTTOM))
    mark = square_mark(art)
    png_path = os.path.join(ROOT, "assets", "app_icon.png")
    ico_path = os.path.join(ROOT, "assets", "app_icon.ico")
    mark.save(png_path)
    mark.save(ico_path, sizes=ICO_SIZES)
    print("wrote", png_path, mark.size)
    print("wrote", ico_path,
          f"{os.path.getsize(ico_path) / 1024:.0f} KB", [s[0] for s in ICO_SIZES])


if __name__ == "__main__":
    main()
