"""
Genera la sección de SILLERÍA a partir de la lista de precios en PDF del proveedor.

Uso:
    pip install pymupdf pillow
    python tools/build_sillas.py "ruta/Lista de precios Sillería.pdf"

Produce:
    assets/js/silleria-data.js      -> modelos, características y tapicerías (SIN precios)
    assets/img/sillas/*.webp        -> fotos optimizadas

Se omiten a propósito: precios, tiempos de embarque, garantías, piezas por caja,
políticas de venta, datos bancarios, accesorios Sophia y cualquier mención del
proveedor. El PDF NO debe subirse al repositorio (está en .gitignore).
"""
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_JS = ROOT / "assets" / "js" / "silleria-data.js"
OUT_IMG = ROOT / "assets" / "img" / "sillas"
IMG_MAX = 900

# Páginas que no se usan: portadas de "nuevo producto" (repiten modelos y traen marca del
# proveedor) y la última sección (accesorios Sophia, políticas, envíos y datos bancarios).
SKIP_PAGES = set(range(1, 6)) | {53, 54}

# Nombres que en el PDF están como dibujo (no como texto): (página, posición en la página).
MISSING_NAMES = {
    (6, 0): "Sofá Nest Lateral", (6, 1): "Sofá Nest Esquinero", (6, 2): "Sofá Nest Individual",
    (11, 3): "Nexus 1 Plaza", (11, 4): "Nexus 2 Plazas",
    (43, 4): "Mesa Chic Central", (44, 0): "Mesa Chic Esquinera",
}

CATEGORIES = [
    {"id": "sillas-oficina", "portada": "SIL-SOUL-EXPRESS-BLACK-RESPALDO-ALTO", "name": "Sillas de oficina",
     "blurb": "Sillas ejecutivas y operativas con mecanismos synchro y reclinables, respaldo de malla o tapizado."},
    {"id": "sillas-visita", "portada": "SIL-DELTA-BLACK-VISITA", "name": "Sillas de visita",
     "blurb": "Sillas fijas para recepción, salas de juntas y atención a clientes."},
    {"id": "sillas-multiusos", "portada": "SIL-KICCA-TRINEO", "name": "Sillas multiusos y apilables",
     "blurb": "Sillas para cafetería, comedor, capacitación y áreas comunes; muchas son apilables."},
    {"id": "bancos", "portada": "SIL-KICCA-BANCO", "name": "Bancos y periqueras",
     "blurb": "Bancos altos para barras, cocinetas y mostradores."},
    {"id": "sillones-lounge", "portada": "SIL-VIBE-TRINEO", "name": "Sillones lounge y de espera",
     "blurb": "Sillones tapizados para recepción, salas de espera y zonas de descanso."},
    {"id": "sofas", "portada": "SIL-SOFA-JOY-DOS-PLAZAS", "name": "Sofás y salas",
     "blurb": "Sofás de 1 a 3 plazas, sistemas modulares, poufs y mesas de centro."},
]

EJECUTIVAS = {"Legend", "Omega", "Dream", "CEO", "President", "Class", "Bond", "Skin I", "Royal",
              "Advance", "Boss", "Soul", "Spirit", "Epic"}
MULTIUSOS = {"Shine", "Rise", "Kicca", "Kalea", "Vela", "Pixel", "Art", "Icon", "Token", "Smart", "Flex", "Swap"}
LOUNGE = {"Vibe", "Orbit", "Luna", "Swing", "Zen", "Quest", "Eva", "Edge", "Pulse", "Glam", "Aura", "Enigma",
          "Kinzika", "Kimbra", "Flok", "Extrakool", "Bakko", "Bakkone", "Hub", "Shell", "City", "Space",
          "Switch", "Infinite", "Nexus"}
TWO_WORD_FAMILIES = ("Soul Express", "Spirit Express", "Skin I", "Mesa Chic", "Banco Row", "Banco Steel")

PRICE = re.compile(r"^\$[\d,]+(\.\d+)?$")
NOISE = re.compile(r"(precios de lista|^características|express \(3|producción \(10|precio especial|"
                   r"costo de envío|nuevo producto|mínimo de piezas|l i sta|tiempo de entrega|embarque|garant)", re.I)
# Marcas del proveedor que NO deben aparecer en el sitio. Se leen de un archivo local
# (tools/marcas_excluidas.txt, fuera del repositorio) para no publicarlas en GitHub.
# Formato, una por línea:   marca            -> se elimina
#                           Material=Reemplazo -> se sustituye (ej. "XyzLeather=Piel sintética")
MARCAS_FILE = Path(__file__).with_name("marcas_excluidas.txt")
if not MARCAS_FILE.exists():
    raise SystemExit(f"Falta {MARCAS_FILE}: crea el archivo con las marcas del proveedor a excluir (ver README).")
BANNED, MARCAS_FIXES = [], []
for raw in MARCAS_FILE.read_text(encoding="utf-8").splitlines():
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        continue
    word, _, repl = raw.partition("=")
    BANNED.append(word.strip().lower())
    MARCAS_FIXES.append((re.compile(re.escape(word.strip()) + r"\w*" if not repl else re.escape(word.strip()), re.I), repl.strip()))
# Las sustituciones (con "=") van antes que las eliminaciones.
MARCAS_FIXES.sort(key=lambda f: f[1] == "")
BRAND_FIXES = MARCAS_FIXES + [(re.compile(r"Genuine Leather", re.I), "piel genuina"),
               (re.compile(r"Ladrilllo"), "Ladrillo"), (re.compile(r" o, "), " o "), (re.compile(r"Vino,,"), "Vino,"),
               (re.compile(r"\btrinero\b"), "trineo")]


def clean(s):
    s = unicodedata.normalize("NFKC", s).replace("\xa0", " ")
    for pat, rep in BRAND_FIXES:
        s = pat.sub(rep, s)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,/")
    return s


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").upper()


def page_lines(p):
    out = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).replace("\xa0", " ").strip()
            if t:
                out.append((pymupdf.Rect(l["bbox"]), t, max(s["size"] for s in l["spans"])))
    return out


def group_cells(lines):
    """Agrupa las líneas de opciones (tapicerías) en celdas por columna y cercanía vertical."""
    cols = []
    for r, t, _ in sorted(lines, key=lambda x: x[0].x0):
        for c in cols:
            if abs(c["x"] - r.x0) <= 6:
                c["items"].append((r, t))
                break
        else:
            cols.append({"x": r.x0, "items": [(r, t)]})
    res = []
    for c in cols:
        cur, last = [], None
        for r, t in sorted(c["items"], key=lambda x: x[0].y0):
            if last is not None and r.y0 - last > 7:
                res.append((cur[0][0], [x for _, x in cur]))
                cur = []
            cur.append((r, t))
            last = r.y1
        if cur:
            res.append((cur[0][0], [x for _, x in cur]))
    res.sort(key=lambda x: (round(x[0].y0 / 4), x[0].x0))
    return [ts for _, ts in res]


VERSION_LABELS = re.compile(r"^(asiento y respaldo tapizados?( en)?:?|asiento tapizado( en)?:?|sin tapiz|"
                            r"\d plazas?|pouf( chico| grande)?|sofá modular|mesa modular|mesa auxiliar|"
                            r"descansabrazos|paleta opcional|multicontacto opcional|taburete .*)$", re.I)


def cell_text(lines):
    """Convierte una celda en (versión, tapicería) legibles."""
    lines = [clean(l) for l in lines if clean(l)]
    version = None
    if lines and VERSION_LABELS.match(lines[0]):
        version = lines.pop(0).rstrip(":")
    if not lines:
        return version, None
    head = lines[0]
    rest = lines[1:]
    text = head
    for l in rest:
        if text.endswith((" de", " para", ",", "/")) or l[:1].islower():
            text = text + " " + l
        elif text.endswith(":") or re.match(r"^Grado \d$", text):
            text = text.rstrip(":") + ": " + l
        elif ":" in text:
            text += ", " + l
        else:
            text += ", " + l
    text = re.sub(r",\s*,", ",", text).replace(" /,", " /").strip(" ,/")
    text = re.sub(r"Pranna,? Vinil grado 3 tipo contract, ideal para espacios de alto tráfico",
                  "Pranna (vinil tipo contract, ideal para alto tráfico)", text)
    text = text.replace(" o, ", " o ").replace("Gris, Claro", "Gris claro").replace("Gris, Oxford", "Gris Oxford")
    text = text[:1].upper() + text[1:]
    if text.lower() == "colores de línea":
        text = "Colores de línea (concha sin tapizar)"
    return version, text


def family_of(name):
    for fam in TWO_WORD_FAMILIES:
        if name.startswith(fam):
            return fam
    if name.startswith("Sofá "):
        return " ".join(name.split()[:2])
    return name.split()[0]


def category_of(name, fam):
    n = name.lower()
    if name.startswith(("Sofá", "Mesa Chic")) or name == "Nexus 2 Plazas":
        return "sofas", "Mesa de centro" if "mesa" in n else ("Pouf" if "pouf" in n else "Sofá")
    if "banco" in n or name in ("Altra", "Epic Alta"):
        return "bancos", "Banco alto"
    if "visita" in n or fam == "Virtu":
        return "sillas-visita", "Visita"
    if fam in MULTIUSOS:
        return "sillas-multiusos", "Con paleta" if fam in ("Smart", "Flex") else (
            "Plegable / apilable" if fam in ("Swap",) else "Multiusos")
    if fam in LOUNGE:
        return "sillones-lounge", "Sillón" if fam not in ("Hub", "Shell", "Space", "City") else "Lounge giratoria"
    return "sillas-oficina", "Ejecutiva" if fam in EJECUTIVAS else "Operativa"


def save_image(doc, xref, path):
    info = doc.extract_image(xref)
    im = Image.open(io.BytesIO(info["image"])).convert("RGB")
    diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L")
    bbox = diff.point(lambda v: 255 if v > 18 else 0).getbbox()
    if bbox:
        im = ImageOps.expand(im.crop(bbox), border=round(max(im.size) * 0.04), fill=(255, 255, 255))
    im.thumbnail((IMG_MAX, IMG_MAX), Image.LANCZOS)
    im.save(path, "WEBP", quality=82, method=6)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    doc = pymupdf.open(sys.argv[1])
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for old in OUT_IMG.glob("*.webp"):
        old.unlink()

    products, seen = [], set()
    for pn in range(1, doc.page_count + 1):
        if pn in SKIP_PAGES:
            continue
        p = doc[pn - 1]
        lines = page_lines(p)
        imgs = sorted(
            [(p.get_image_bbox(x), x[0]) for x in p.get_images(full=True)
             if p.get_image_bbox(x).x0 < 60 and p.get_image_bbox(x).width < 160 and p.get_image_bbox(x).height > 60],
            key=lambda t: t[0].y0)
        heads = [l for l in lines if l[0].x0 < 60 and 6.5 <= l[2] <= 9]
        starts, names, prev_bottom = [], [], 0
        for i, (bb, _) in enumerate(imgs):
            cand = [h for h in heads if prev_bottom - 2 <= h[0].y0 < bb.y0]
            if cand:
                starts.append(cand[-1][0].y0)
                names.append(cand[-1][1])
            else:
                starts.append(bb.y0 - 12)
                names.append(MISSING_NAMES.get((pn, i)))
            prev_bottom = bb.y1

        for i, (bb, xref) in enumerate(imgs):
            name = clean(names[i] or "")
            if not name:
                raise SystemExit(f"Producto sin nombre en página {pn}, posición {i}: agrégalo a MISSING_NAMES")
            name = re.sub(r"\s+–\s+", " · ", name)
            top, bottom = starts[i], (starts[i + 1] if i + 1 < len(imgs) else 10_000)
            region = [l for l in lines if top <= l[0].y0 < bottom and l[0].x0 > bb.x1 - 2]
            car = next((l for l in region if l[1].startswith("Características")), None)
            pre = next((l for l in region if l[1].startswith("Precios de Lista")), None)
            feats, opts = [], []
            for r, t, s in sorted(region, key=lambda l: (l[0].y0, l[0].x0)):
                if NOISE.search(t) or PRICE.match(t):
                    continue
                if car and pre and car[0].y0 < r.y0 < pre[0].y0:
                    feats.append(clean(t))
                elif pre and r.y0 > pre[0].y0:
                    opts.append((r, t, s))
            # Características partidas en dos líneas ("Base:" + detalle)
            merged = []
            for f in feats:
                if merged and (merged[-1].endswith(":") or f[:1].islower()):
                    merged[-1] = (merged[-1] + " " + f).strip()
                elif f:
                    merged.append(f)
            versiones, tapices = [], []
            for cell in group_cells(opts):
                v, t = cell_text(cell)
                if v:
                    v = re.sub(r"\s+en$", "", v)
                    v = "Taburete a juego (opcional)" if v.lower().startswith("taburete") else v[:1].upper() + v[1:].lower()
                    # Las filas "1 Plaza", "Pouf", etc. ya están en el nombre del producto.
                    if v not in versiones and not re.match(r"^(\d plazas?|pouf.*|sofá modular|mesa .*|descansabrazos)$", v, re.I):
                        versiones.append(v)
                if not t:
                    continue
                if t.startswith("Vinil grado 3") and tapices and tapices[-1] == "Pranna":
                    tapices[-1] = "Pranna (vinil tipo contract, ideal para alto tráfico)"
                    continue
                g = re.match(r"^(Grado \d): (.*)$", t)
                prev = next((i for i, x in enumerate(tapices) if g and x.startswith(g.group(1) + ":")), None)
                if prev is not None:
                    if g.group(2) not in tapices[prev]:
                        tapices[prev] += ", " + g.group(2)
                elif t not in tapices:
                    tapices.append(t)

            fam = family_of(name)
            cat, tipo = category_of(name, fam)
            sku = "SIL-" + slug(name)
            if sku in seen:
                sku += f"-{pn}"
            seen.add(sku)
            img = f"{slug(name).lower()}.webp"
            save_image(doc, xref, OUT_IMG / img)
            products.append({
                "sku": sku, "cat": cat, "tipo": tipo, "nombre": name, "familia": fam,
                "medidas": None, "descripcion": " ".join(merged), "caracteristicas": merged,
                "versiones": versiones,
                "tapices": tapices, "img": "sillas/" + img,
            })

    order = {c["id"]: i for i, c in enumerate(CATEGORIES)}
    products.sort(key=lambda p: order[p["cat"]])
    text = json.dumps(products, ensure_ascii=False)
    for bad in BANNED + ["$", "embarque", "garantía"]:
        if bad in text.lower():
            raise SystemExit(f"Quedó información no permitida en los datos: {bad!r}")
    skus = {p["sku"] for p in products}
    cats = []
    for c in CATEGORIES:
        c = dict(c, grupo="silleria", count=sum(p["cat"] == c["id"] for p in products))
        if c.get("portada") not in skus:
            c.pop("portada", None)
        cats.append(c)
    OUT_JS.write_text(
        "/* Generado por tools/build_sillas.py — no editar a mano. */\n"
        "window.RUAV_SILLERIA = Object.freeze(" +
        json.dumps({"categorias": cats, "productos": products}, ensure_ascii=False, indent=1) + ");\n",
        encoding="utf-8", newline="\n")
    print(f"{len(products)} productos de sillería -> {OUT_JS}")
    for c in cats:
        print(f"  {c['name']}: {c['count']}")


if __name__ == "__main__":
    main()
