"""
Genera las páginas HTML del sitio a partir de tools/templates/.

El encabezado, pie, panel de cotización y cabecera de seguridad (CSP) viven en
tools/templates/_layout.html; cada página solo define su contenido. Edita las
plantillas y vuelve a ejecutar:

    python tools/build_pages.py
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "tools" / "templates"
SITE_URL = "https://ruav.com.mx/"
layout = (TPL / "_layout.html").read_text(encoding="utf-8")

for page in sorted(TPL.glob("*.html")):
    if page.name.startswith("_"):
        continue
    raw = page.read_text(encoding="utf-8")
    m = re.match(r"\s*<!--(.*?)-->\s*\n", raw, re.S)
    meta = dict(line.split(":", 1) for line in m.group(1).strip().splitlines()) if m else {}
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    content = raw[m.end():] if m else raw
    out = (layout
           .replace("{{title}}", html.escape(meta.get("title", "RUAV Mobiliario")))
           .replace("{{description}}", html.escape(meta.get("description", "")))
           .replace("{{url}}", SITE_URL + ("" if page.name == "index.html" else page.name))
           .replace("{{robots}}", meta.get("robots", "index, follow"))
           .replace("{{nav_catalogo}}", ' aria-current="page"' if meta.get("nav") == "catalogo" else "")
           .replace("{{content}}", content.rstrip()))
    if meta.get("canonical") == "dinamico":
        # La ficha de producto define su URL canónica en app.js (depende de ?sku=).
        out = re.sub(r'\n  <meta property="og:url"[^>]*>\n  <link rel="canonical"[^>]*>', "", out)
    (ROOT / page.name).write_text(out, encoding="utf-8", newline="\n")
    print("ok", page.name)
