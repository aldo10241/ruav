"""
Genera el catálogo del sitio a partir de la lista de precios de RUAV (.xlsx).

Uso:
    pip install pillow
    python tools/build_catalog.py "ruta/lista de precios RUAV 2026 SIN PRECIOS.xlsx"

Produce:
    assets/js/catalogo-data.js      -> datos de productos (sin precios)
    assets/img/productos/*.webp     -> imágenes optimizadas, nombradas por clave

El .xlsx NO debe subirse al repositorio (está en .gitignore).
"""
import io
import json
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_JS = ROOT / "assets" / "js" / "catalogo-data.js"
OUT_IMG = ROOT / "assets" / "img" / "productos"
IMG_MAX_W = 900

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Categorías en el orden del catálogo. "match" = texto del encabezado de sección (sin espacios).
CATEGORIES = [
    {"id": "escritorios", "match": "ESCRITORIOSTIPOGRAPA", "name": "Escritorios tipo grapa",
     "blurb": "Escritorios 100 % desarmables con faldón de refuerzo, en medidas de 1.20 a 2.40 m."},
    {"id": "mesas-asamblea", "match": "MESASDEASAMBLEACONBASESTIPOTOTEM", "name": "Mesas de asamblea",
     "blurb": "Mesas para sala de juntas con bases tipo tótem y paso de cableado, de 2.40 a 5.40 m."},
    {"id": "barras-altas", "match": "BARRASALTASTIPOGRAPA", "name": "Barras altas",
     "blurb": "Barras autosoportantes de 1.10 m de altura y sus extensiones para espacios colaborativos."},
    {"id": "credenzas", "match": "CREDENZAS", "name": "Credenzas",
     "blurb": "Credenzas bajas y de altura escritorio con puertas, cajones y espacios abiertos."},
    {"id": "cubiertas", "match": "CUBIERTAS", "name": "Cubiertas",
     "blurb": "Cubiertas en panel melamínico de 28 mm con cantos de PVC de 2 mm al tono."},
    {"id": "pedestales", "match": "PEDESTALES", "name": "Pedestales",
     "blurb": "Pedestales fijos y móviles con cajón papelero, archivo suspendido y cerradura."},
    {"id": "archiveros", "match": "ARCHIVEROS", "name": "Archiveros",
     "blurb": "Archiveros de 2, 3 y 4 gavetas para tamaño carta u oficio, con correderas de extensión total."},
    {"id": "almacenamiento", "match": "UNIDADESDEALMACENAMIENTO", "name": "Unidades de almacenamiento",
     "blurb": "Libreros y gabinetes abiertos o con puertas, en alturas de 0.72 a 2.00 m."},
    {"id": "gabinetes-superiores", "match": "GABINETESSUPERIORES", "name": "Gabinetes superiores",
     "blurb": "Gabinetes aéreos para muro, abiertos o con puertas abatibles de cierre suave."},
    {"id": "lockers", "match": "LOCKERS", "name": "Lockers",
     "blurb": "Torres de lockers de 2 a 12 puertas con cerradura sencilla o de rulinas."},
]

# Nombre corto y "tipo" (para filtrar) según el prefijo de la clave.
TYPES = {
    "CUBREC": ("Cubierta rectangular", "Rectangular"),
    "CUBCUA": ("Cubierta cuadrada", "Cuadrada"),
    "PM1P1A": ("Pedestal móvil 1 papelero + 1 archivo", "Móvil con cajones"),
    "PF2P1A": ("Pedestal fijo 2 papeleros + 1 archivo", "Fijo con cajones"),
    "PM1PAB": ("Pedestal móvil con cajón papelero", "Móvil con cajones"),
    "PMABIE": ("Pedestal abierto móvil", "Abierto"),
    "PMABEN": ("Pedestal abierto móvil con repisa", "Abierto"),
    "CRABAB": ("Credenza baja 2 espacios abiertos", "Credenza baja"),
    "CRABPU": ("Credenza baja abierta + 2 puertas", "Credenza baja"),
    "CRPUAB": ("Credenza baja 2 puertas + abierta", "Credenza baja"),
    "CRABCA": ("Credenza baja abierta + 2 cajones", "Credenza baja"),
    "CRCAAB": ("Credenza baja 2 cajones + abierta", "Credenza baja"),
    "CRPUPU": ("Credenza 4 puertas", "Credenza 0.75 m"),
    "CRPUAA": ("Credenza 2 puertas + 2 archiveros", "Credenza 0.75 m"),
    "CRAAPU": ("Credenza 2 archiveros + 2 puertas", "Credenza 0.75 m"),
    "CPULPA": ("Credenza 2 puertas + lapicero, papelero y archivero", "Credenza 0.75 m"),
    "CLPAPU": ("Credenza lapicero, papelero y archivero + 2 puertas", "Credenza 0.75 m"),
    "ESCGRA": ("Escritorio tipo grapa", "Escritorio"),
    "EGFC-2": ("Escritorio tipo grapa", "Escritorio"),
    "EGFC-1": ("Escritorio tipo grapa", "Escritorio"),
    "BAAUSO": ("Barra alta autosoportante", "Barra alta"),
    "EXAUSO": ("Extensión para barra alta", "Extensión"),
    "LORU": ("Locker {n} puertas · cerradura de rulinas", "Cerradura de rulinas"),
    "LOCS": ("Locker {n} puertas · cerradura sencilla", "Cerradura sencilla"),
    "LOLLMC": ("Llave maestra para cerradura de rulinas", "Accesorios"),
    "ARCH2G": ("Archivero de 2 gavetas", "Archivero"),
    "ARCH3G": ("Archivero de 3 gavetas", "Archivero"),
    "ARCH4G": ("Archivero de 4 gavetas", "Archivero"),
    "UALMAB": ("Unidad de almacenamiento abierta", "Abierta"),
    "UALMPU": ("Unidad de almacenamiento con puertas", "Con puertas"),
    "GASUAB": ("Gabinete superior abierto", "Abierto"),
    "GASUPU": ("Gabinete superior con puertas", "Con puertas"),
    "GASUAP": ("Gabinete superior abierto + puertas", "Mixto"),
    "GASUPA": ("Gabinete superior puertas + abierto", "Mixto"),
    "MEASTO": ("Mesa de asambleas base tótem", "Mesa de asambleas"),
}

# Correcciones de ortografía/acentos en las descripciones del Excel.
FIXES = [
    (r"\bmelaminico\b", "melamínico"), (r"\bcajon\b", "cajón"), (r"\bextension\b", "extensión"),
    (r"\bExtension\b", "Extensión"), (r"\bplastico\b", "plástico"), (r"\bfaldon\b", "faldón"),
    (r"\bfaldones\b", "faldones"), (r"\btotem\b", "tótem"), (r"\baccion\b", "acción"),
    (r"\bdefrente\b", "de frente"), (r"\bDesarmable\b", "desarmable"), (r"\bLockers\b", "lockers"),
    (r"(\d\.\d{2}) mm\b", r"\1 m"),  # "1.00 x 0.60 mm" en el Excel son metros
    (r"\s+([.,])", r"\1"), (r"\.\s*\.", "."), (r"\s{2,}", " "),
]


def clean_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").strip()
    for pat, rep in FIXES:
        s = re.sub(pat, rep, s)
    return s.strip()


def parse_dims(s: str):
    nums = [int(n) for n in re.findall(r"\d+", s or "")]
    if len(nums) != 3 or not all(nums):
        return None
    return {"frente": nums[0], "fondo": nums[1], "alto": nums[2]}


def read_xlsx(path: Path):
    z = zipfile.ZipFile(path)
    shared = [
        "".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml"))
    ]
    rows = {}
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{{{NS_MAIN}}}row"):
        rn = int(r.get("r"))
        for c in r.findall(f"{{{NS_MAIN}}}c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find(f"{{{NS_MAIN}}}v")
            if v is not None:
                val = shared[int(v.text)] if c.get("t") == "s" else v.text
            else:
                isel = c.find(f"{{{NS_MAIN}}}is")
                if isel is None:
                    continue
                val = "".join(t.text or "" for t in isel.iter(f"{{{NS_MAIN}}}t"))
            rows.setdefault(rn, {})[col] = (val or "").strip()

    rels = {
        rel.get("Id"): "xl/media/" + rel.get("Target").split("/")[-1]
        for rel in ET.fromstring(z.read("xl/drawings/_rels/drawing1.xml.rels"))
    }
    images = {}
    for anchor in ET.fromstring(z.read("xl/drawings/drawing1.xml")):
        frm = anchor.find(f"{{{NS_XDR}}}from")
        blip = anchor.find(f".//{{{NS_A}}}blip")
        if frm is None or blip is None:
            continue
        row = int(frm.find(f"{{{NS_XDR}}}row").text) + 1
        images.setdefault(row, rels[blip.get(f"{{{NS_R}}}embed")])
    return z, rows, images


def type_for(sku: str):
    for key in sorted(TYPES, key=len, reverse=True):
        if sku.startswith(key):
            name, tipo = TYPES[key]
            if "{n}" in name:
                m = re.match(r"LO(?:RU|CS)(\d+)", sku)
                name = name.format(n=m.group(1) if m else "")
            return name, tipo
    raise SystemExit(f"Prefijo sin nombre definido en TYPES: {sku}")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    z, rows, images = read_xlsx(Path(sys.argv[1]))
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for old in OUT_IMG.glob("*.webp"):
        old.unlink()

    cat_by_match = {c["match"]: c for c in CATEGORIES}
    products, current, seen = [], None, set()
    for rn in sorted(rows):
        r = rows[rn]
        sku = r.get("C", "")
        if not sku:
            header = re.sub(r"\s+", "", r.get("B", ""))
            if header in cat_by_match:
                current = cat_by_match[header]
            continue
        if current is None or sku == "CLAVE":
            continue
        if not re.fullmatch(r"[A-Z0-9-]{6,24}", sku) or sku in seen:
            raise SystemExit(f"Clave inválida o repetida en fila {rn}: {sku!r}")
        seen.add(sku)

        name, tipo = type_for(sku)
        img_name = None
        if rn in images:
            im = Image.open(io.BytesIO(z.read(images[rn]))).convert("RGB")
            # Recorta el margen blanco para que todas las piezas se vean del mismo tamaño.
            diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L")
            bbox = diff.point(lambda v: 255 if v > 24 else 0).getbbox()
            if bbox:
                im = ImageOps.expand(im.crop(bbox), border=round(max(im.size) * 0.03), fill=(255, 255, 255))
            if im.width > IMG_MAX_W:
                im = im.resize((IMG_MAX_W, round(im.height * IMG_MAX_W / im.width)), Image.LANCZOS)
            img_name = f"{sku}.webp"
            im.save(OUT_IMG / img_name, "WEBP", quality=82, method=6)

        products.append({
            "sku": sku,
            "cat": current["id"],
            "tipo": tipo,
            "nombre": name,
            "medidas": parse_dims(r.get("D", "")),
            "descripcion": clean_text(r.get("E", "")),
            "img": img_name,
        })

    order = {c["id"]: i for i, c in enumerate(CATEGORIES)}
    products.sort(key=lambda p: order[p["cat"]])  # orden estable: respeta el orden del Excel dentro de cada categoría
    cats = [{k: c[k] for k in ("id", "name", "blurb")} | {"count": sum(p["cat"] == c["id"] for p in products)}
            for c in CATEGORIES]
    data = {"categorias": cats, "productos": products}
    OUT_JS.write_text(
        "/* Generado por tools/build_catalog.py — no editar a mano. */\n"
        "window.RUAV_CATALOGO = Object.freeze(" + json.dumps(data, ensure_ascii=False, indent=1) + ");\n",
        encoding="utf-8",
    )
    print(f"{len(products)} productos, {sum(1 for p in products if p['img'])} imágenes -> {OUT_JS}")


if __name__ == "__main__":
    main()
