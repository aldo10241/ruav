"""
Genera la segunda línea de SILLERÍA (proveedor B) a partir de dos PDF del proveedor:
  1) Lista de precios (texto): SKU, descripción, precio sugerido y foto por renglón.
  2) Catálogo general (páginas en imagen): características, descripción y medidas (vía OCR de Windows).

Uso:
    pip install pymupdf pillow numpy winocr
    python tools/build_sillas_b.py "ruta/Lista_Precios.pdf" "ruta/Catalogo_General.pdf"

Produce:
    assets/js/silleria-b-data.js    -> modelos con precio sugerido (+ IVA), sin "Su precio" ni tiempos de entrega
    assets/img/sillas-b/*.webp      -> fotos
    tools/reporte_sillas_b.txt      -> reporte local para revisar SKU, precio, categoría, foto y textos (no se publica)

Solo se toma la sillería (secciones de sillería y salas de espera de la lista; sección SILLERÍA del
catálogo). El OCR se guarda en tools/.ocr_catalogo_b.json para no repetirlo.
"""
import asyncio
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_JS = ROOT / "assets" / "js" / "silleria-b-data.js"
OUT_IMG = ROOT / "assets" / "img" / "sillas-b"
OCR_CACHE = ROOT / "tools" / ".ocr_catalogo_b.json"
REPORT = ROOT / "tools" / "reporte_sillas_b.txt"
CAT_PAGES = range(10, 115)   # sección SILLERÍA del catálogo 2026
IMG_MAX = 900

# Secciones de la lista de precios que son asientos.
SEAT_SECTION = re.compile(r"(Sillería|Salas? de Espera)", re.I)
# Renglones que no son asientos aunque estén en esas secciones (accesorios).
EXCLUDE_SKUS = {"345"}            # brazo intermedio para banca
# De "Plegables" solo se toman las sillas (no las mesas).
PLEGABLES = re.compile(r"Plegables$")

# Productos sin foto en la lista ni en el catálogo: se usa la foto de un modelo hermano
# como "imagen de referencia" (se indica en la ficha). Clave -> clave con foto.
REF_IMAGES = {
    "798": "518", "799": "519", "800": "520", "765": "524", "766": "525", "767": "526",
    "706": "355", "721": "276", "795": "694", "298": "297", "701": "277",
}

# Recortes manuales (página del catálogo, caja en fracciones del ancho/alto de la página) para fotos que
# el recorte automático no resuelve bien (páginas con varios modelos o texto pegado a la foto).
CROP_OVERRIDES = {
    "295": (102, (0.08, 0.13, 0.42, 0.37)), "294": (102, (0.08, 0.60, 0.42, 0.82)),
    "1014": (90, (0.06, 0.60, 0.42, 0.82)),
    "509": (107, (0.48, 0.19, 0.84, 0.39)), "511": (107, (0.20, 0.66, 0.82, 0.88)),
    "529": (105, (0.20, 0.72, 0.84, 0.92)),
}

# Correcciones de errores típicos del OCR en las características.
OCR_FIXES = [
    # Errores del OCR (verificados contra el catálogo)
    (r"\b3600\b", "360°"), (r"\b360ü\b", "360°"), (r"\b1700\b", "170°"), (r"nivel y 5", "nivel 0, 1 y 5"),
    # Erratas del propio catálogo
    (r"\bPistóno\b", "Pistón"), (r"\bAiento\b", "Asiento"), (r"triplay domados", "triplay doblados"),
    (r"rompimiento, regado,", "rompimiento, rasgado,"), (r"Mecanismo de bloque o de YR021", "Mecanismo de bloqueo YR021"),
    (r"(\d) kg/m\.", r"\1 kg/m³."), (r"Descanzabrazos", "Descansabrazos"), (r"Descansa brazos", "Descansabrazos"),
    (r"Asiento Unido", "Asiento unido"),
    (r"\bKg\b", "kg"), (r"(\d)kg\b", r"\1 kg"), (r"^\.\s*", ""), (r"\s+([.,;:])", r"\1"), (r"\s{2,}", " "),
]

# Medidas con error en el propio catálogo (SKU -> medida corregida).
DIM_OVERRIDES = {
    "288": {"alto": "93 - 117.5 cm"},   # el catálogo dice 177.5 cm; su gemela 287 dice 117.5 cm
}

PRICE = re.compile(r"^\$[\d,]+\.\d{2}$")

# Marcas del proveedor que no deben publicarse: se leen del archivo local tools/marcas_excluidas.txt
# (no se sube al repositorio). Solo se usan las palabras sin "=".
MARCAS_FILE = Path(__file__).with_name("marcas_excluidas.txt")
if not MARCAS_FILE.exists():
    raise SystemExit(f"Falta {MARCAS_FILE} (ver README)")
BANNED = [l.split("=")[0].strip().lower() for l in MARCAS_FILE.read_text(encoding="utf-8").splitlines()
          if l.strip() and not l.startswith("#") and "=" not in l]
SKU_RE = re.compile(r"SKU\W{0,3}([0-9IOl]{2,5})", re.I)


def fix_mojibake(s):
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def money_to_float(t):
    return float(t.replace("$", "").replace(",", ""))


# ---------------------------------------------------------------- lista de precios

def read_price_list(path):
    d = pymupdf.open(path)
    rows = []
    for pn in range(1, d.page_count + 1):
        p = d[pn - 1]
        lines = []
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t:
                    lines.append((pymupdf.Rect(l["bbox"]), fix_mojibake(t)))
        section = next((t for r, t in lines if 70 <= r.y0 <= 80 and r.x0 < 40), "")
        if not SEAT_SECTION.search(section) and not PLEGABLES.search(section):
            continue
        imgs = [(p.get_image_bbox(x), x[0]) for x in p.get_images(full=True) if p.get_image_bbox(x).y0 > 95]
        for r, sku in [(r, t) for r, t in lines if 88 <= r.x0 <= 100 and r.y0 > 100 and r.y1 < 730]:
            row = [(rr, t) for rr, t in lines if abs(rr.y0 - r.y0) < 3]
            # La descripción puede ocupar 2 renglones (el segundo, ~7 pt más abajo).
            desc = " ".join(t for rr, t in sorted(lines, key=lambda x: x[0].y0)
                            if 130 <= rr.x0 < 380 and -3 < rr.y0 - r.y0 < 11)
            sug = [t for rr, t in row if 470 <= rr.x0 < 520 and PRICE.match(t)]
            img = [x for bb, x in imgs if bb.y0 - 3 <= r.y0 <= bb.y1]
            if not sku.isdigit() or not sug:
                raise SystemExit(f"Renglón ilegible en página {pn}: {sku!r} {desc!r}")
            if PLEGABLES.search(section) and not re.search(r"\bsilla\b", desc, re.I):
                continue
            if sku in EXCLUDE_SKUS:
                continue
            rows.append({"page": pn, "section": section, "sku": sku, "desc": desc,
                         "sugerido": money_to_float(sug[0]), "xref": img[0] if img else None})
    skus = [r["sku"] for r in rows]
    if len(skus) != len(set(skus)):
        raise SystemExit("Hay claves repetidas en la lista de precios")
    return d, rows


# ---------------------------------------------------------------- catálogo (OCR)

def ocr_catalog(path):
    cache = json.loads(OCR_CACHE.read_text(encoding="utf-8")) if OCR_CACHE.exists() else {}
    if cache.get("_source") == Path(path).name and all(str(p) in cache for p in CAT_PAGES):
        return cache
    import winocr
    d = pymupdf.open(path)
    cache = {"_source": Path(path).name}

    async def run():
        for pn in CAT_PAGES:
            pix = d[pn - 1].get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            res = await winocr.recognize_pil(img, "es")
            cache[str(pn)] = [{"x": round(l.words[0].bounding_rect.x), "y": round(l.words[0].bounding_rect.y),
                               "h": round(max(w.bounding_rect.height for w in l.words)), "t": l.text} for l in res.lines]
    asyncio.run(run())
    OCR_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def sku_num(s):
    return str(int(s.replace("I", "1").replace("l", "1").replace("O", "0")))


def parse_catalog(o):
    cat, feats = {}, {}
    for pn in CAT_PAGES:
        L = o.get(str(pn), [])
        for l in L:
            m = SKU_RE.search(l["t"])
            if not m:
                continue
            sku = sku_num(m.group(1))
            c = 0 if l["x"] < 760 else 1
            same = [x for x in L if (0 if x["x"] < 760 else 1) == c]
            above = [x for x in same if x["y"] < l["y"] and l["y"] - x["y"] < 260]
            big = [x for x in above if x["h"] >= 30]
            ty = max(big, key=lambda x: x["y"]) if big else None
            fam = [x["t"] for x in above if x["t"].startswith("Familia")]
            nxt = [x["y"] for x in same if SKU_RE.search(x["t"]) and x["y"] > l["y"]]
            lim = min(nxt) if nxt else 10 ** 6
            dims = {}
            for x in same:
                if l["y"] < x["y"] < lim:
                    mm = re.match(r"(Alto|Ancho|Profundidad)\s*:\s*(.+)", x["t"])
                    if mm and mm.group(1).lower() not in dims:
                        dims[mm.group(1).lower()] = mm.group(2).strip()
            cat.setdefault(sku, []).append({"page": pn, "x": l["x"], "y": l["y"], "col": c,
                                            "title": ty["t"] if ty else "", "title_y": ty["y"] if ty else l["y"] - 150,
                                            "familia": fam[-1].replace("Familia", "").strip() if fam else "", "dims": dims})

    def desc_of(L):
        h = next((x for x in L if re.search(r"Descripci[oó]n$", x["t"].strip())), None)
        if not h:
            return ""
        lines = [x["t"] for x in sorted(L, key=lambda x: x["y"])
                 if x["y"] > h["y"] + 20 and abs(x["x"] - h["x"]) < 80 and x["h"] < 30 and "colores del producto" not in x["t"]]
        return re.sub(r"\s+", " ", " ".join(lines)).strip()

    for pn in CAT_PAGES:
        L = o.get(str(pn), [])
        heads = sorted([x for x in L if re.search(r"Caracter[ií]sticas", x["t"])], key=lambda x: x["y"])
        sku_lines = [(x, sku_num(SKU_RE.search(x["t"]).group(1))) for x in L if SKU_RE.search(x["t"])]
        prev = sorted({s for s, v in cat.items() if any(e["page"] == pn - 1 for e in v)})
        d = desc_of(L)
        targets_desc = [s for _, s in sku_lines] if len(sku_lines) == 1 else (prev if not sku_lines and len(prev) == 1 else [])
        for s in targets_desc:
            if d:
                feats.setdefault(s, {}).setdefault("descripcion", d)
        for i, h in enumerate(heads):
            ymax = heads[i + 1]["y"] if i + 1 < len(heads) else 10 ** 6
            items, cur = [], None
            for x in sorted([x for x in L if h["y"] + 20 < x["y"] < ymax and abs(x["x"] - h["x"]) < 120
                             and "colores del producto" not in x["t"]], key=lambda x: x["y"]):
                t = x["t"].strip()
                # El OCR a veces lee la viñeta como "." o la omite antes de "Peso:".
                bullet = re.match(r"^[•·*.]\s*", t) or re.match(r"^peso:", t, re.I)
                t = re.sub(r"^[•·*.]\s*", "", t)
                t = t[:1].upper() + t[1:] if re.match(r"^peso:", t, re.I) else t
                # Nuevo punto si trae viñeta, o si el anterior ya terminó en punto y este empieza con mayúscula;
                # si no, es continuación del renglón anterior.
                if cur is None or bullet or (cur.endswith(".") and t[:1].isupper()):
                    if cur:
                        items.append(cur)
                    cur = t
                else:
                    cur += " " + t
            if cur:
                items.append(cur)
            above = [(x, s) for x, s in sku_lines if x["y"] < h["y"]]
            if above:
                target = [max(above, key=lambda t: t[0]["y"])[1]]
            elif not sku_lines and len(prev) == 1:
                target = prev
            elif len(sku_lines) == 1:
                target = [sku_lines[0][1]]
            else:
                target = []
            for s in target:
                feats.setdefault(s, {}).setdefault("caracteristicas", [i for i in items if len(i) > 2])
    return cat, feats


# ---------------------------------------------------------------- textos, categorías y familias

FAMILY_WORDS = ["Allegro", "Genova", "Regia", "Clasica", "Tiempo", "Industrial", "Brecia", "Orozco", "Zalce", "Kahlo",
                "Alfaro", "Tamayo", "Etna", "Vista", "Magnus", "Alfa", "Eames", "Organic", "Nexus", "Nitro", "Milan",
                "Patri", "Lite", "Air", "Volt", "Alce", "Braun", "Egipto", "Star", "Tenerife", "Mediterraneo", "Imanet",
                "Airport", "Transit", "Attesa", "Confort", "Olson"]


def clean_name(desc):
    s = unicodedata.normalize("NFC", desc)
    s = re.sub(r"^\d+\.\d+(?=[A-Za-z])", "", s)           # "1401.59Silla..." (dato pegado en el PDF)
    for w in BANNED:                                        # marcas del proveedor (archivo local)
        s = re.sub(r"\b" + re.escape(w) + r"\b", "", s, flags=re.I)
    s = re.sub(r"SillaOperativa", "Silla Operativa", s)
    s = re.sub(r"\bVsita\b", "Visita", s)
    s = re.sub(r"\bViniPiel\b", "Vinipiel", s, flags=re.I)
    s = re.sub(r"\bc/b\b", "con brazos", s)
    s = re.sub(r"\bs/b\b", "sin brazos", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .")
    if s.isupper():
        s = s.capitalize()
        s = re.sub(r"\b(e\d{3}|s\d+)\b", lambda m: m.group(1).upper(), s)
    # Nombres de modelo siempre con mayúscula inicial ("eames" -> "Eames").
    for w in FAMILY_WORDS:
        s = re.sub(r"\b" + w + r"\b", w, s, flags=re.I)
    s = re.sub(r"\bDescanzabrazos\b", "Descansabrazos", s)
    s = re.sub(r"\b(sofa|Sofa)\b", "Sofá", s)
    s = re.sub(r"\b(Sillon)\b", "Sillón", s)
    s = re.sub(r"\bClasica\b", "Clásica", s)
    s = re.sub(r"\bMediterraneo\b", "Mediterráneo", s)
    s = re.sub(r"\bPlastico\b", "Plástico", s, flags=re.I)
    return s[:1].upper() + s[1:]


def family_of(name, catfam):
    if catfam:
        return re.sub(r"\s+", " ", catfam).strip()
    n = name
    for w in FAMILY_WORDS:
        if re.search(r"\b" + w + r"\b", n.replace("á", "a").replace("Clásica", "Clasica"), re.I):
            return w if w not in ("Clasica", "Mediterraneo") else {"Clasica": "Clásica", "Mediterraneo": "Mediterráneo"}[w]
    for pat, fam in [(r"Mod\.\s*91[123]\b", "Attesa"), (r"\bE1\d\d\b", "Serie E"), (r"\bH\d+(PU)?\b", "Serie H"), (r"\bKB-\d+\b", "Serie KB"),
                     (r"\bT[HAB]\d+V?\b", "Serie T"), (r"\bS\d{2}\b|\bS3\b", "Serie S"), (r"\bH?VL\d+", "Serie VL")]:
        if re.search(pat, n):
            return fam
    return name


def category_of(name):
    n = name.lower()
    if "banca" in n:
        return "sillones-lounge", "Banca de espera"
    if "attesa" in n or "mod. 912" in n:
        return "sillones-lounge", "Sillón modular"
    if re.search(r"\bsof[aá]\b", n) or ("sillón" in n and "plaza" in n):
        return "sofas", "Sofá"
    if "mesa banco" in n or "mesabanco" in n or "escolar" in n:
        return "sillas-multiusos", "Con paleta"
    if "plegable" in n or "banquetera" in n or "estibable" in n:
        return "sillas-multiusos", "Plegable / apilable"
    if "cajero" in n or "banco alto" in n:
        return "bancos", "Silla cajero"
    if "visita" in n:
        return "sillas-visita", "Visita"
    if "ejecutiv" in n:
        return "sillas-oficina", "Ejecutiva"
    if "operativa" in n or "secretarial" in n:
        return "sillas-oficina", "Operativa"
    raise SystemExit(f"No sé en qué categoría va: {name!r} (agrega una regla en category_of)")


def fix_text(s):
    s = unicodedata.normalize("NFC", s)
    for pat, rep in OCR_FIXES:
        s = re.sub(pat, rep, s)
    return s.strip()


def clean_feature(s):
    """Limpia un punto de características: quita restos de las etiquetas de íconos que el OCR pega
    al final y descarta fragmentos ilegibles."""
    s = fix_text(s)
    # Texto suelto después del último punto (etiquetas de íconos como "de Inclinación").
    m = re.match(r"^(.*\.)\s+([^.]{1,40})$", s)
    if m and not re.search(r"\d", m.group(2)):
        s = m.group(1)
    if not s or s[:1].islower() or re.search(r"[*'()\[\]{}|]|[a-z][A-Z]{2}", s) or len(s) < 8:
        return None
    # Etiquetas de íconos de "Funciones" que el OCR lee como texto suelto (sin punto final).
    if not s.endswith(".") and re.match(r"^(Control|Inclinaci|Reclinaci|Ajuste|Giratori|Altura|Funciones|Mecanismo de Reclin)", s):
        return None
    return s if s.endswith((".", ":")) else s + "."


def fix_dim(v):
    v = fix_text(v).replace("¯", "-").replace("_", ".")
    v = re.sub(r"\bIII\b", "111", v)
    v = re.sub(r"(\d+)\s+S\b", r"\1.5", v)                      # "97 S" -> "97.5"
    v = re.sub(r"\b1\s(\d{2})\b", r"1\1", v)                     # "1 54" -> "154"
    # El OCR pierde el punto decimal: "835" -> "83.5", "1015" -> "101.5" (ninguna medida pasa de 300 cm).
    v = re.sub(r"\b(\d{3,4})\b", lambda m: str(int(m.group(1)) / 10).rstrip("0").rstrip(".") if int(m.group(1)) >= 300 else m.group(1), v)
    v = re.sub(r"\s*-\s*", " - ", v).strip()
    if not v.endswith("cm"):
        v = v.replace("cm", "").strip() + " cm"
    return re.sub(r"(\d)cm", r"\1 cm", v)


# ---------------------------------------------------------------- imágenes

def save_webp(im, path):
    im = im.convert("RGB")
    diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L")
    bbox = diff.point(lambda v: 255 if v > 18 else 0).getbbox()
    if bbox:
        im = ImageOps.expand(im.crop(bbox), border=round(max(im.size) * 0.04), fill=(255, 255, 255))
    im.thumbnail((IMG_MAX, IMG_MAX), Image.LANCZOS)
    im.save(path, "WEBP", quality=82, method=6)


def crop_from_catalog(cdoc, entry=None, single_on_page=False, page=None, box_frac=None):
    """Recorta la foto principal de un modelo en una página del catálogo: el bloque de pixeles
    no blancos más grande dentro de la zona del modelo (así se descartan textos y la franja del borde)."""
    pix = cdoc[(page or entry["page"]) - 1].get_pixmap(dpi=200)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    W, H = im.size
    if box_frac:
        box = (int(box_frac[0] * W), int(box_frac[1] * H), int(box_frac[2] * W), int(box_frac[3] * H))
    elif single_on_page:
        box = (0, int(H * 0.08), W, int(H * 0.66))
    else:
        x0 = 0 if entry["col"] == 0 else W // 2
        box = (x0, max(0, entry["title_y"] - 40), x0 + W // 2, min(H, entry["y"] + 1000))
    # Nunca incluir los márgenes laterales (franja de color del catálogo).
    box = (max(box[0], int(W * 0.045)), box[1], min(box[2], int(W * 0.955)), box[3])
    region = np.asarray(im.crop(box).convert("L"))
    cell = 8
    h, w = region.shape[0] // cell, region.shape[1] // cell
    grid = (region[:h * cell, :w * cell].reshape(h, cell, w, cell) < 225).mean(axis=(1, 3)) > 0.08
    seen = np.zeros_like(grid)
    best = None
    for i in range(h):
        for j in range(w):
            if grid[i, j] and not seen[i, j]:
                stack, cells = [(i, j)], []
                seen[i, j] = True
                while stack:
                    a, b = stack.pop()
                    cells.append((a, b))
                    for da in (-1, 0, 1):
                        for db in (-1, 0, 1):
                            na, nb = a + da, b + db
                            if 0 <= na < h and 0 <= nb < w and grid[na, nb] and not seen[na, nb]:
                                seen[na, nb] = True
                                stack.append((na, nb))
                if best is None or len(cells) > len(best):
                    best = cells
    if not best:
        return None
    ys, xs = [c[0] for c in best], [c[1] for c in best]
    bb = (box[0] + min(xs) * cell, box[1] + min(ys) * cell, box[0] + (max(xs) + 1) * cell, box[1] + (max(ys) + 1) * cell)
    return im.crop(bb)


# ---------------------------------------------------------------- principal

def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    pdoc, rows = read_price_list(sys.argv[1])
    cdoc = pymupdf.open(sys.argv[2])
    cat, feats = parse_catalog(ocr_catalog(sys.argv[2]))

    # Fichas compartidas: modelos con el mismo título en el catálogo comparten características/descripción.
    by_title = {}
    for s, entries in cat.items():
        for e in entries:
            if e["title"]:
                by_title.setdefault(e["title"], set()).add(s)
    for skus in by_title.values():
        src = next((feats[s] for s in sorted(skus) if s in feats and feats[s].get("caracteristicas")), None)
        for s in skus:
            if src and not feats.get(s, {}).get("caracteristicas"):
                feats.setdefault(s, {}).update({k: v for k, v in src.items()})

    # Variantes del mismo modelo (mismo código, p. ej. "TH06" negra/gris) comparten la ficha si una no la trae.
    # Solo dentro del mismo tipo de silla (la TH03 ejecutiva y la TH03 de visita son fichas distintas).
    def model_key(desc):
        n = clean_name(desc)
        code = re.search(r"\b(T[HAB]\d+V?|H\d+(?:PU)?|E1\d\d|S\d{1,2}|KB-\d+)\b", n)
        kind = "visita" if "visita" in n.lower() else ("cajero" if "cajero" in n.lower() else "otra")
        return (code.group(1), kind) if code else None
    groups = {}
    for r in rows:
        k = model_key(r["desc"])
        if k:
            groups.setdefault(k, []).append(r["sku"])
    for skus in groups.values():
        src = next((feats[s] for s in skus if feats.get(s, {}).get("caracteristicas")), None)
        for s in skus:
            if src and not feats.get(s, {}).get("caracteristicas"):
                feats.setdefault(s, {})["caracteristicas"] = src["caracteristicas"]
                if src.get("descripcion") and not feats[s].get("descripcion"):
                    feats[s]["descripcion"] = src["descripcion"]

    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for old in OUT_IMG.glob("*.webp"):
        old.unlink()

    products, report, skipped = [], [], []
    page_counts = {}
    for s, entries in cat.items():
        for e in entries:
            page_counts[e["page"]] = page_counts.get(e["page"], 0) + 1
    by_sku = {r["sku"]: r for r in rows}

    for r in rows:
        name = clean_name(r["desc"])
        entries = cat.get(r["sku"], [])
        entry = entries[0] if entries else None
        fam = family_of(name, entry["familia"] if entry else "")
        img_name, img_note = f"{r['sku']}.webp", ""
        if r["xref"]:
            save_webp(Image.open(io.BytesIO(pdoc.extract_image(r["xref"])["image"])), OUT_IMG / img_name)
            img_note = "lista de precios"
        elif r["sku"] in CROP_OVERRIDES:
            pg, frac = CROP_OVERRIDES[r["sku"]]
            save_webp(crop_from_catalog(cdoc, page=pg, box_frac=frac), OUT_IMG / img_name)
            img_note = f"catálogo p.{pg} (recorte manual)"
        elif entry:
            single = page_counts.get(entry["page"], 0) == 1
            crop = crop_from_catalog(cdoc, entry, single)
            if crop is None:
                raise SystemExit(f"No se pudo recortar la foto de {r['sku']} (catálogo p.{entry['page']})")
            save_webp(crop, OUT_IMG / img_name)
            img_note = f"catálogo p.{entry['page']}"
        elif r["sku"] in REF_IMAGES and by_sku.get(REF_IMAGES[r["sku"]], {}).get("xref"):
            ref = by_sku[REF_IMAGES[r["sku"]]]
            save_webp(Image.open(io.BytesIO(pdoc.extract_image(ref["xref"])["image"])), OUT_IMG / img_name)
            img_note = f"REFERENCIA (foto de {ref['sku']})"
        else:
            skipped.append(f"{r['sku']} | {name} | ${r['sugerido']:,.2f} | sin foto en lista ni catálogo")
            continue
        cid, tipo = category_of(name)

        f = feats.get(r["sku"], {})
        caracteristicas = [c for c in (clean_feature(x) for x in f.get("caracteristicas", [])) if c]
        caracteristicas = [x for x in caracteristicas if not re.match(r"^(Alto|Ancho|Profundidad)\b", x)]
        dims = dict(entry["dims"]) if entry else {}
        dims = {k: fix_dim(v) for k, v in dims.items()}
        dims.update(DIM_OVERRIDES.get(r["sku"], {}))
        medidas = [f"{k.capitalize()}: {dims[k]}" for k in ("alto", "ancho", "profundidad") if k in dims]
        descripcion = fix_text(f.get("descripcion", "")) or name
        products.append({
            "sku": "SIL-B-" + r["sku"], "clave": r["sku"], "cat": cid, "tipo": tipo, "nombre": name, "familia": fam,
            "medidas": None, "dimensiones": medidas, "descripcion": descripcion,
            "caracteristicas": caracteristicas, "versiones": [], "tapices": [],
            "precios": [{"opcion": "Precio sugerido", "precio": r["sugerido"]}], "desde": r["sugerido"],
            "iva": "más IVA", "img": "sillas-b/" + img_name, "imgRef": img_note.startswith("REFERENCIA"),
        })
        report.append(f"{r['sku']:>5} | p.{r['page']:>2} | ${r['sugerido']:>10,.2f} | {cid}/{tipo} | {fam} | {name}\n"
                      f"        foto: {img_note} | medidas: {', '.join(medidas) or '—'}\n"
                      + "".join(f"        · {c}\n" for c in caracteristicas))

    order = ["sillas-oficina", "sillas-visita", "sillas-multiusos", "bancos", "sillones-lounge", "sofas"]
    products.sort(key=lambda p: order.index(p["cat"]))
    text = json.dumps(products, ensure_ascii=False)
    if re.search("|".join([re.escape(w) for w in BANNED] + [r"su precio", r"t\.e\.[is]"]), text, re.I):
        raise SystemExit("Quedó información no permitida (marca del proveedor, 'Su precio' o tiempos de entrega)")
    OUT_JS.write_text("/* Generado por tools/build_sillas_b.py — no editar a mano. */\n"
                      "window.RUAV_SILLERIA_B = Object.freeze(" + json.dumps({"productos": products}, ensure_ascii=False, indent=1) + ");\n",
                      encoding="utf-8", newline="\n")
    REPORT.write_text("Revisión de sillería (proveedor B): clave | página lista | precio sugerido | categoría | familia | nombre\n\n"
                      + "\n".join(report) + "\n\nOMITIDOS (sin foto):\n" + "\n".join(skipped) + "\n", encoding="utf-8")
    print(f"{len(products)} productos -> {OUT_JS}; omitidos sin foto: {len(skipped)}; reporte: {REPORT}")


if __name__ == "__main__":
    main()
