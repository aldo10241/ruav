"""Genera versiones web del logo (fondo transparente) a partir de tools/logo-original.webp."""
from pathlib import Path
from PIL import Image, ImageChops
ROOT = Path(__file__).resolve().parent.parent
src = Image.open(ROOT / "tools" / "logo-original.webp").convert("RGB")
px = src.load()
w, h = src.size
out = Image.new("RGBA", (w, h))
op = out.load()
for y in range(h):
    for x in range(w):
        r, g, b = px[x, y]
        mx, mn = max(r, g, b), min(r, g, b)
        sat = mx - mn
        # Rojo: alta saturación. Plata: alta luminosidad con baja saturación. Fondo: oscuro y neutro.
        a = max((sat - 45) / 70, (mx - 92) / 55)
        a = max(0.0, min(1.0, a))
        op[x, y] = (r, g, b, int(a * 255))
bbox = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
out = out.crop((max(bbox[0]-8,0), max(bbox[1]-8,0), min(bbox[2]+8,w), min(bbox[3]+8,h)))
dst = ROOT / "assets" / "img"
out.save(dst / "logo-ruav.png", optimize=True)
out.resize((640, round(out.height * 640 / out.width)), Image.LANCZOS).save(dst / "logo-ruav.webp", "WEBP", quality=90)
# favicon: la "R" roja
sq = out.crop((0, 0, out.height, out.height)).resize((180, 180), Image.LANCZOS)
bg = Image.new("RGBA", (180, 180), (22, 22, 22, 255)); bg.alpha_composite(sq)
bg.save(dst / "apple-touch-icon.png"); bg.resize((32, 32), Image.LANCZOS).save(dst / "favicon-32.png")
# Imagen para redes sociales (Open Graph) con el logo original
og = Image.new("RGB", (1200, 630), (20, 18, 17)); lg = src.resize((1100, round(src.height*1100/src.width)), Image.LANCZOS)
og.paste(lg, (50, (630-lg.height)//2)); og.save(dst / "og-ruav.jpg", quality=85)
print(out.size)
