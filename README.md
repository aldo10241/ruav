# RUAV Mobiliario — sitio web

Catálogo en línea de mobiliario de oficina con **cotización por WhatsApp**. Es un sitio estático
(HTML, CSS y JavaScript sin dependencias), pensado para publicarse en **GitHub Pages**.

## Estructura

```
index.html, catalogo.html, producto.html,     ← páginas generadas (no editar a mano)
aviso-de-privacidad.html, 404.html
assets/
  css/styles.css                               ← estilos
  js/config.js                                 ← DATOS DEL NEGOCIO (WhatsApp, teléfono, correo…)
  js/catalogo-data.js                          ← catálogo generado desde el Excel
  js/app.js                                    ← lógica: catálogo, filtros, ficha, cotización
  img/                                         ← logo, íconos, imágenes de productos
tools/
  build_catalog.py                             ← Excel → catálogo + imágenes
  build_pages.py                               ← plantillas → páginas HTML
  make_logo.py                                 ← genera logo transparente, favicon e imagen para redes
  templates/                                   ← plantillas de las páginas (_layout.html = encabezado/pie/CSP)
.github/workflows/pages.yml                    ← publicación automática en GitHub Pages
```

## 1. Configurar los datos del negocio

Edita **`assets/js/config.js`**:

- `whatsapp`: número en formato internacional, solo dígitos (México: `52` + 10 dígitos).
- `telefono`, `email`, `direccion`, `horario`: se muestran en el sitio; si se dejan vacíos, se ocultan.
- `sitioUrl`: `https://ruav.com.mx` (en stage se cambia sola a `https://stage.ruav.com.mx`).

Completa también los datos entre corchetes del **aviso de privacidad**
(`tools/templates/aviso-de-privacidad.html`). El correo de `.well-known/security.txt` es
`contacto@ruav.com.mx`: créalo o redirígelo (Cloudflare → Email → Email Routing es gratis).

## 2. Actualizar el catálogo

Cuando el cliente envíe una nueva lista de precios (mismo formato de Excel):

```bash
pip install pillow
python tools/build_catalog.py "ruta/lista de precios RUAV 2026 SIN PRECIOS.xlsx"
```

El script lee claves, medidas, descripciones e imágenes del Excel; corrige acentos comunes,
recorta y optimiza las imágenes a WebP y regenera `assets/js/catalogo-data.js`.
Si aparece una clave con un prefijo nuevo, agrégalo al diccionario `TYPES` del script.

> ⚠️ El Excel **nunca** debe subirse al repositorio (está en `.gitignore`).

## 3. Editar páginas

Modifica las plantillas en `tools/templates/` y ejecuta:

```bash
python tools/build_pages.py
```

## 4. Ver el sitio localmente

```bash
python -m http.server 8080 --bind 127.0.0.1
```

y abre <http://localhost:8080>.

## 5. Ramas y ambientes

| Rama | Ambiente | URL | Workflow |
| --- | --- | --- | --- |
| `main` | Producción | https://ruav.com.mx | `.github/workflows/pages.yml` |
| `stage` | Pruebas | https://stage.ruav.com.mx | `.github/workflows/stage.yml` |

Flujo de trabajo:

1. Trabaja siempre sobre `stage` (o en una rama nueva que luego se une a `stage`).
2. `git push` a `stage` → en ~1 minuto se publica en **stage.ruav.com.mx** (con aviso
   “AMBIENTE DE PRUEBAS”, sin indexar en Google y con los enlaces de WhatsApp apuntando a stage).
3. Cuando esté aprobado, abre un **Pull Request `stage` → `main`** en GitHub y únelo.
   Eso publica en producción.

Solo se publican los archivos públicos (`tools/prepare_site.sh`); `tools/`, el README y
`.claude/` nunca salen al sitio.

## 6. Publicar producción en GitHub Pages

1. En el repositorio: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Settings → Environments → github-pages → Deployment branches**: deja solo `main`.
3. Haz `push` a `main` (o ejecuta el workflow “Publicar producción” desde la pestaña *Actions*).

## 7. Dominio ruav.com.mx en Cloudflare

**a) Verificar el dominio en GitHub** (impide que otra cuenta lo use en sus Pages):

1. GitHub → tu foto → **Settings → Pages → Add a domain** → escribe `ruav.com.mx`.
2. GitHub muestra un registro **TXT** (`_github-pages-challenge-<usuario>`). Créalo en
   Cloudflare → **DNS → Records → Add record** (tipo TXT, nombre y contenido exactos).
3. Regresa a GitHub y presiona **Verify**.

**b) Registros DNS en Cloudflare** (DNS → Records). Todos con **Proxy status: DNS only (nube gris)**,
para que GitHub pueda emitir y renovar el certificado HTTPS:

| Tipo | Nombre | Contenido |
| --- | --- | --- |
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| AAAA | `@` | `2606:50c0:8000::153` |
| AAAA | `@` | `2606:50c0:8001::153` |
| AAAA | `@` | `2606:50c0:8002::153` |
| AAAA | `@` | `2606:50c0:8003::153` |
| CNAME | `www` | `<usuario>.github.io` |
| CNAME | `stage` | `<usuario>.github.io` |

Si existen registros previos de “parking” para `@` o `www`, bórralos.

**c) Conectar el dominio en el repositorio:** **Settings → Pages → Custom domain** → `ruav.com.mx` →
**Save**. Espera a que el chequeo DNS salga en verde (minutos a 1 hora) y activa **Enforce HTTPS**.
`www.ruav.com.mx` redirigirá solo a `ruav.com.mx`.

**d) Recomendado en Cloudflare:**
- **DNS → Settings → DNSSEC → Enable** (Cloudflare lo configura solo si el dominio está registrado ahí).
- Registro **CAA**: nombre `@`, etiqueta `issue`, valor `letsencrypt.org` (la autoridad que usa GitHub).

## 8. Ambiente de stage (configuración única)

GitHub Pages solo permite un sitio por repositorio, por eso stage se publica en un
**segundo repositorio** (ej. `<usuario>/ruav-stage`):

1. Crea el repositorio **`ruav-stage`** (vacío, público; Pages gratis requiere público).
2. Genera una llave SSH **exclusiva** para el despliegue (en tu computadora):
   ```bash
   ssh-keygen -t ed25519 -C "deploy ruav-stage" -N "" -f ruav_stage_deploy
   ```
3. En **ruav-stage → Settings → Deploy keys → Add deploy key**: pega el contenido de
   `ruav_stage_deploy.pub` y marca **Allow write access**.
4. En el repositorio principal → **Settings → Secrets and variables → Actions**:
   - pestaña *Secrets* → **New repository secret** `STAGE_DEPLOY_KEY` = contenido de `ruav_stage_deploy` (la privada).
   - pestaña *Variables* → **New repository variable** `STAGE_REPO` = `<usuario>/ruav-stage`.
5. **Borra** los dos archivos de la llave de tu computadora.
6. Haz `push` a `stage`. Cuando el workflow termine, en **ruav-stage → Settings → Pages**:
   *Source: Deploy from a branch* → rama `gh-pages` / `(root)`. El dominio `stage.ruav.com.mx`
   se toma del archivo `CNAME`; espera el chequeo DNS y activa **Enforce HTTPS**.

La llave solo puede escribir en `ruav-stage`: si se filtrara, no da acceso al repositorio principal.

Opcional: para que solo tu equipo vea stage, se puede proteger con **Cloudflare Zero Trust → Access**
(gratis hasta 50 usuarios), lo que requiere activar el proxy (nube naranja) en el registro `stage`
y poner **SSL/TLS → Full (strict)**.

## Seguridad

### Ya implementado en el código

| Medida | Para qué sirve |
| --- | --- |
| **Content-Security-Policy** estricta (`default-src 'none'`, solo scripts/estilos/imágenes propios) | Bloquea la inyección de scripts (XSS) y la carga de recursos externos |
| Cero scripts, fuentes o CDNs de terceros | Sin riesgo de cadena de suministro ni rastreo de terceros |
| Contenido dinámico creado con `textContent`/`createElement` (nunca `innerHTML`) | Impide que parámetros de la URL o datos guardados ejecuten código |
| Validación de parámetros (`?sku=`, `?cat=`, filtros) contra el catálogo | Entradas inválidas se descartan |
| Validación del almacenamiento local (solo claves existentes, cantidades 1–999) | Datos alterados no rompen el sitio |
| Sin formularios que envíen datos a un servidor; datos del cliente solo viajan en el mensaje que él envía | No se almacenan datos personales; nada que filtrar |
| Enlaces externos con `rel="noopener noreferrer"` y `Referrer-Policy` | Evita *tabnabbing* y fuga de URLs |
| Protección anti-*clickjacking* por JavaScript | GitHub Pages no permite la cabecera `X-Frame-Options` |
| Workflow con permisos mínimos y `persist-credentials: false` | Reduce el impacto si una acción se ve comprometida |
| `.gitignore` para Excel/CSV/PDF/.env | Evita publicar listas de precios o secretos por accidente |
| `security.txt` | Canal para reportar vulnerabilidades |

### Pendiente en la cuenta de GitHub (hazlo antes de publicar)

- [ ] Activar **autenticación de dos factores (2FA)** en todas las cuentas con acceso al repositorio.
- [ ] **Branch protection** en `main`: requerir pull request y bloquear *force push*.
- [ ] **Verificar el dominio** en *Settings → Pages* de la cuenta/organización (evita que otro repositorio lo secuestre).
- [ ] Activar **Enforce HTTPS** en Pages.
- [ ] Activar **Secret scanning** y **Push protection** (*Settings → Code security*).
- [ ] En *Settings → Actions*, permitir solo acciones de GitHub y verificadas.
- [ ] En el DNS: registro **CAA** que solo autorice a `letsencrypt.org` y, si el proveedor lo ofrece, **DNSSEC**.

### Opcional: cabeceras HTTP completas

GitHub Pages no permite cabeceras personalizadas. Si se quiere `Strict-Transport-Security`,
`X-Frame-Options`, `Permissions-Policy` y `X-Content-Type-Options` reales, se puede poner
**Cloudflare** (plan gratuito) delante del dominio y agregarlas con *Transform Rules*.

## Siguiente fase: tienda en línea

Un sitio estático no puede procesar pagos de forma segura por sí mismo. Cuando el cliente
confirme la tienda, lo recomendable es usar un **checkout alojado por el proveedor**
(Mercado Pago, Stripe Payment Links o Shopify Buy Button): el pago ocurre en su plataforma
certificada y este sitio nunca toca datos de tarjetas. La lista de cotización actual ya
funciona como base para el carrito.
