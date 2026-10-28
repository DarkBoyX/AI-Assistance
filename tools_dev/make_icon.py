"""Generates assets/vega.ico (run automatically by build.bat)."""
from pathlib import Path
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, S - 8, S - 8), fill=(10, 10, 12, 255))
for r, a, w in ((104, 255, 9), (76, 170, 8), (48, 100, 7)):
    d.ellipse((S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r), outline=(111, 208, 255, a), width=w)
out = Path(__file__).resolve().parent.parent / "assets" / "vega.ico"
out.parent.mkdir(exist_ok=True)
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote", out)
