#!/usr/bin/env bash
# Copia solo los archivos públicos a _site/ para publicarlos.
#   bash tools/prepare_site.sh production   -> https://ruav.com.mx
#   bash tools/prepare_site.sh stage        -> https://stage.ruav.com.mx (sin indexar en buscadores)
set -euo pipefail

TARGET="${1:-production}"
OUT="_site"

rm -rf "$OUT"
mkdir "$OUT"
cp index.html catalogo.html producto.html aviso-de-privacidad.html 404.html robots.txt sitemap.xml "$OUT"/
cp -r assets .well-known "$OUT"/
touch "$OUT/.nojekyll"

if [ "$TARGET" = "stage" ]; then
  STAGE_URL="https://stage.ruav.com.mx"
  # Enlaces de WhatsApp apuntan a stage
  sed -i "s|sitioUrl: \"https://ruav.com.mx\"|sitioUrl: \"$STAGE_URL\"|" "$OUT/assets/js/config.js"
  grep -q "sitioUrl: \"$STAGE_URL\"" "$OUT/assets/js/config.js"
  # Que los buscadores no indexen stage
  printf 'User-agent: *\nDisallow: /\n' > "$OUT/robots.txt"
  rm -f "$OUT/sitemap.xml" "$OUT/.well-known/security.txt"
  for f in "$OUT"/*.html; do
    sed -i 's|<meta name="robots" content="[^"]*">|<meta name="robots" content="noindex, nofollow">|' "$f"
    sed -i 's|<span class="hide-sm">[^<]*</span>|<span><strong>AMBIENTE DE PRUEBAS (STAGE)</strong></span>|' "$f"
  done
  # Dominio de GitHub Pages para el repositorio de stage (publicación desde rama)
  echo "stage.ruav.com.mx" > "$OUT/CNAME"
fi

echo "Sitio ($TARGET) listo en $OUT/"
