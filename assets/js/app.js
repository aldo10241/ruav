/*
 * RUAV Mobiliario — lógica del sitio.
 *
 * Seguridad: todo el contenido dinámico se crea con createElement/textContent
 * (nunca innerHTML), los parámetros de la URL y el almacenamiento local se validan
 * contra el catálogo, y no se usan scripts ni recursos de terceros.
 */
(function () {
  "use strict";

  // Protección contra clickjacking: GitHub Pages no permite la cabecera X-Frame-Options.
  if (window.top !== window.self) {
    document.documentElement.style.display = "none";
    try { window.top.location.replace(window.self.location.href); } catch (e) { /* bloqueado */ }
    return;
  }

  var CFG = window.RUAV_CONFIG || {};
  var DATA = window.RUAV_CATALOGO || { categorias: [], productos: [] };
  var SILLERIA = window.RUAV_SILLERIA || { categorias: [], productos: [] };
  // Segunda línea de sillería (otro proveedor): usa las mismas categorías de Sillería.
  var SILLERIA_B = (window.RUAV_SILLERIA_B || { productos: [] }).productos.map(function (p) { return Object.assign({ linea: "b" }, p); });
  var PRODUCTS = DATA.productos.concat(SILLERIA.productos, SILLERIA_B);
  var CATS = DATA.categorias.map(function (c) { return Object.assign({ grupo: "mobiliario" }, c); }).concat(SILLERIA.categorias)
    .map(function (c) {
      return Object.assign({}, c, { count: PRODUCTS.filter(function (p) { return p.cat === c.id; }).length });
    });
  var GRUPOS = [
    { id: "mobiliario", name: "Mobiliario", blurb: "Escritorios, mesas de juntas, credenzas, almacenamiento, lockers y más, en panel melamínico." },
    { id: "silleria", name: "Sillería", blurb: "Sillas de oficina, visita y multiusos, bancos, sillones lounge y sofás. Elige tu modelo y tapicería y cotiza por WhatsApp." },
  ];
  var BY_SKU = new Map(PRODUCTS.map(function (p) { return [p.sku, p]; }));
  var CAT_BY_ID = new Map(CATS.map(function (c) { return [c.id, c]; }));
  var GRUPO_BY_ID = new Map(GRUPOS.map(function (g) { return [g.id, g]; }));
  var ACABADOS = window.RUAV_ACABADOS || [];
  var ACAB_BY_NAME = new Map(ACABADOS.map(function (a) { return [a.nombre, a]; }));
  var AVISO_EXISTENCIAS = "Sujeto a existencias: no todos los acabados se fabrican en todos los espesores (19 y 28 mm). Confirmamos disponibilidad al cotizar.";
  var IMG_DIR = "assets/img/productos/";
  var ICONS = "assets/img/icons.svg#";
  var SKU_RE = /^[A-Z0-9-]{6,60}$/;
  var WA_NUMBER = /^\d{10,15}$/.test(CFG.whatsapp || "") ? CFG.whatsapp : "";
  var STORE_KEY = "ruav_cotizacion_v1";
  var MAX_QTY = 999;
  var MAX_ITEMS = 60;

  /* ---------------- Utilidades DOM ---------------- */

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) child.forEach(function (c) { append(el, c); });
    else el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  function icon(name, cls) {
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    if (cls) svg.setAttribute("class", cls);
    var use = document.createElementNS(NS, "use");
    use.setAttribute("href", ICONS + name);
    svg.appendChild(use);
    return svg;
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function normalize(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  // Texto escrito por el usuario: sin caracteres de control y con longitud limitada.
  function cleanInput(s, max) {
    return String(s || "").replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, "").trim().slice(0, max);
  }
  function clampQty(n) {
    n = parseInt(n, 10);
    if (!isFinite(n) || n < 1) return 1;
    return Math.min(n, MAX_QTY);
  }

  /* ---------------- Formato de producto ---------------- */

  function fmtLen(mm) {
    if (mm < 100) return mm + " mm";
    return (mm / 1000).toFixed(2) + " m";
  }
  function dimLabels(p) {
    if (!p.medidas) return [];
    var m = p.medidas;
    var third = p.cat === "cubiertas" ? ["Grosor", m.alto] : ["Alto", m.alto];
    return [["Frente", m.frente], ["Fondo", m.fondo], third];
  }
  function dimsShort(p) {
    if (!p.medidas) return "";
    var m = p.medidas;
    return [m.frente, m.fondo, m.alto].map(function (v) { return v < 100 ? v + " mm" : (v / 1000).toFixed(2); }).join(" × ") +
      (m.alto < 100 ? "" : " m");
  }
  function productUrl(p) { return "producto.html?sku=" + encodeURIComponent(p.sku); }
  function catalogUrl(params) {
    var q = new URLSearchParams(params || {}).toString();
    return "catalogo.html" + (q ? "?" + q : "");
  }
  function img(p, cls, eager) {
    return h("img", {
      src: p.img ? (p.img.indexOf("/") > -1 ? "assets/img/" + p.img : IMG_DIR + p.img) : "assets/img/logo-ruav.webp",
      alt: p.nombre + " " + dimsShort(p),
      class: cls,
      loading: eager ? "eager" : "lazy",
      decoding: "async",
      width: 900, height: 600,
    });
  }
  function absoluteUrl(path) {
    var base = /^https:\/\/[^\s"'<>]+$/.test(CFG.sitioUrl || "") ? CFG.sitioUrl.replace(/\/$/, "") + "/" : location.origin + location.pathname.replace(/[^/]*$/, "");
    return base + path;
  }

  /* ---------------- WhatsApp ---------------- */

  function waLink(text) {
    var base = WA_NUMBER ? "https://wa.me/" + WA_NUMBER : "https://wa.me/";
    return base + "?text=" + encodeURIComponent(text);
  }
  function isSilla(p) { return !!p.familia; }
  // Opción elegida por el cliente: acabado (mobiliario) o tapicería (sillería).
  function optionLabel(p) { return isSilla(p) ? "Tapicería" : "Acabado"; }
  // Opciones con precio de una silla (sin los adicionales como "Paleta opcional").
  function priceOptions(p) {
    return (p.precios || []).filter(function (x) { return x.opcion.indexOf("(adicional)") === -1; });
  }
  function extrasOf(p) {
    return (p.precios || []).filter(function (x) { return x.opcion.indexOf("(adicional)") > -1; });
  }
  function priceOf(p, opcion) {
    var o = priceOptions(p).find(function (x) { return x.opcion === opcion; });
    return o ? o.precio : null;
  }
  var MXN = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
  var MXN2 = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // Precios con centavos se muestran exactos ($3,904.55); los enteros sin decimales ($4,670).
  function money(n) { return Math.round(n * 100) % 100 ? MXN2.format(n) : MXN.format(n); }
  function ivaSuffix(p) { return p.iva ? " + IVA" : ""; }
  // Precio aplicable: el de la opción elegida o, si el modelo tiene un solo precio, ese.
  function unitPrice(p, opcion) {
    var opts = priceOptions(p);
    if (opcion && priceOf(p, opcion) !== null) return priceOf(p, opcion);
    return opts.length === 1 ? opts[0].precio : null;
  }
  var AVISO_PRECIOS = "Precios de lista en pesos mexicanos, sujetos a cambio sin previo aviso. El precio final, IVA, envío y disponibilidad se confirman en tu cotización.";
  var AVISO_PRECIOS_IVA = "Precios de lista en pesos mexicanos, más IVA, sujetos a cambio sin previo aviso. El precio final, envío y disponibilidad se confirman en tu cotización.";
  function avisoFor(p) { return p.iva ? AVISO_PRECIOS_IVA : AVISO_PRECIOS; }
  function validOption(p, opcion) {
    if (!opcion || typeof opcion !== "string") return false;
    return isSilla(p) ? priceOf(p, opcion) !== null : ACAB_BY_NAME.has(opcion);
  }
  function itemKey(sku, opcion) { return sku + "|" + (opcion || ""); }
  function lineFor(p, qty, opcion) {
    var opt = opcion && validOption(p, opcion) ? " — " + optionLabel(p) + ": " + opcion : "";
    if (isSilla(p)) {
      var cat = CAT_BY_ID.get(p.cat);
      if (priceOptions(p).length === 1) opt = "";   // un solo precio: no hay tapicería que elegir
      var precio = unitPrice(p, opcion);
      var ref = precio !== null ? " — Precio de lista: " + money(precio) + ivaSuffix(p) + " c/u" : (p.desde ? " — Desde " + money(p.desde) + ivaSuffix(p) : "");
      return "• " + p.nombre + " (" + (cat ? cat.name : "Sillería") + ")" + (p.clave ? " — Clave " + p.clave : "") + opt + ref + " — Cantidad: " + qty;
    }
    return "• " + p.nombre + " — Clave " + p.sku + (p.medidas ? " (" + dimsShort(p) + ")" : "") + opt + " — Cantidad: " + qty;
  }
  function subtitle(p) { return isSilla(p) ? p.tipo : p.sku; }
  // Imagen representativa de una categoría (definida en los datos o el primer producto).
  function coverOf(c) {
    return (c.portada && BY_SKU.get(c.portada)) || PRODUCTS.find(function (p) { return p.cat === c.id; });
  }
  function singleMessage(p, qty, opcion) {
    return "Hola RUAV, me gustaría cotizar:\n" + lineFor(p, qty || 1, opcion) +
      "\n\nLo vi en: " + absoluteUrl(productUrl(p));
  }
  function waAnchor(text, label, cls) {
    return h("a", {
      class: cls || "btn btn-wa",
      href: waLink(text),
      target: "_blank",
      rel: "noopener noreferrer",
      "aria-label": label,
    }, icon("wa"), cls && cls.indexOf("icon-only") > -1 ? null : label);
  }
  function generalMessage() { return "Hola RUAV, me gustaría recibir información y una cotización de mobiliario."; }

  /* ---------------- Cotización (almacenamiento local) ---------------- */

  var Quote = {
    items: [],
    load: function () {
      var raw = null;
      try { raw = JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); } catch (e) { raw = []; }
      var seen = new Set();
      this.items = (Array.isArray(raw) ? raw : []).filter(function (it) {
        if (!it || typeof it.sku !== "string" || !SKU_RE.test(it.sku) || !BY_SKU.has(it.sku)) return false;
        if (it.opcion && !validOption(BY_SKU.get(it.sku), it.opcion)) it.opcion = "";
        var key = itemKey(it.sku, it.opcion);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, MAX_ITEMS).map(function (it) { return { sku: it.sku, qty: clampQty(it.qty), opcion: it.opcion || "" }; });
    },
    save: function () {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(this.items)); } catch (e) { /* modo privado */ }
      renderQuote();
    },
    find: function (sku, opcion) {
      var key = itemKey(sku, opcion);
      return this.items.find(function (i) { return itemKey(i.sku, i.opcion) === key; });
    },
    add: function (sku, qty, opcion) {
      if (!BY_SKU.has(sku)) return false;
      opcion = validOption(BY_SKU.get(sku), opcion) ? opcion : "";
      var it = this.find(sku, opcion);
      if (it) it.qty = clampQty(it.qty + (qty || 1));
      else {
        if (this.items.length >= MAX_ITEMS) { toast("Tu cotización tiene el máximo de " + MAX_ITEMS + " productos."); return false; }
        this.items.push({ sku: sku, qty: clampQty(qty || 1), opcion: opcion });
      }
      this.save();
      return true;
    },
    set: function (sku, opcion, qty) {
      var it = this.find(sku, opcion);
      if (it) { it.qty = clampQty(qty); this.save(); }
    },
    remove: function (sku, opcion) {
      var key = itemKey(sku, opcion);
      this.items = this.items.filter(function (i) { return itemKey(i.sku, i.opcion) !== key; });
      this.save();
    },
    count: function () { return this.items.reduce(function (a, i) { return a + i.qty; }, 0); },
    has: function (sku) { return this.items.some(function (i) { return i.sku === sku; }); },
  };

  function qtyControl(value, onChange, small) {
    var input = h("input", {
      type: "number", inputmode: "numeric", min: 1, max: MAX_QTY, value: value, "aria-label": "Cantidad",
      onchange: function () { input.value = clampQty(input.value); onChange(+input.value); },
    });
    function step(d) { input.value = clampQty(+input.value + d); onChange(+input.value); }
    return h("div", { class: "qty" + (small ? " sm" : "") },
      h("button", { type: "button", "aria-label": "Quitar uno", text: "−", onclick: function () { step(-1); } }),
      input,
      h("button", { type: "button", "aria-label": "Agregar uno", text: "+", onclick: function () { step(1); } }));
  }

  /* ---------------- Panel de cotización ---------------- */

  var drawer, backdrop, lastFocus;

  function openDrawer() {
    if (!drawer) return;
    lastFocus = document.activeElement;
    backdrop.hidden = false;
    drawer.hidden = false;
    requestAnimationFrame(function () { backdrop.classList.add("show"); drawer.classList.add("open"); });
    document.body.classList.add("no-scroll");
    drawer.setAttribute("aria-hidden", "false");
    setTimeout(function () { $(".drawer-head button", drawer).focus(); }, 50);
  }
  function closeDrawer() {
    if (!drawer || drawer.hidden) return;
    backdrop.classList.remove("show");
    drawer.classList.remove("open");
    document.body.classList.remove("no-scroll");
    drawer.setAttribute("aria-hidden", "true");
    setTimeout(function () { drawer.hidden = true; backdrop.hidden = true; }, 300);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function renderQuote() {
    $all("[data-quote-count]").forEach(function (b) {
      var n = Quote.count();
      b.textContent = String(n);
      b.hidden = n === 0;
      b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump");
    });
    $all("[data-add-sku]").forEach(syncAddButton);
    if (!drawer) return;
    var list = $(".quote-items", drawer);
    var empty = $(".quote-empty", drawer);
    var foot = $(".drawer-foot", drawer);
    var form = $(".quote-form", drawer);
    clear(list);
    var has = Quote.items.length > 0;
    empty.hidden = has;
    foot.hidden = !has;
    form.hidden = !has;
    Quote.items.forEach(function (it) {
      var p = BY_SKU.get(it.sku);
      list.appendChild(h("li", { class: "quote-item" },
        img(p),
        h("div", null,
          h("a", { href: productUrl(p), text: p.nombre }),
          h("div", { class: "pc-sku", text: isSilla(p) ? subtitle(p) : p.sku + " · " + dimsShort(p) }),
          it.opcion ? h("div", { class: "quote-opt", text: optionLabel(p) + ": " + it.opcion }) : null,
          isSilla(p) ? h("div", { class: "quote-opt quote-price", text: unitPrice(p, it.opcion) !== null
            ? "Precio de lista: " + money(unitPrice(p, it.opcion)) + ivaSuffix(p) + " c/u"
            : "Desde " + money(p.desde) + ivaSuffix(p) + " (elige tapicería en la ficha)" }) : null,
          h("div", { class: "quote-item-row" },
            qtyControl(it.qty, function (v) { Quote.set(p.sku, it.opcion, v); }, true),
            h("button", { type: "button", class: "remove-btn", text: "Quitar", "aria-label": "Quitar " + p.nombre + " " + p.sku,
              onclick: function () { Quote.remove(p.sku, it.opcion); } })))));
    });
    var total = $("[data-quote-total]", drawer);
    if (total) total.textContent = Quote.items.length + (Quote.items.length === 1 ? " producto" : " productos") + " · " + Quote.count() + " piezas";
  }

  function sendQuote(ev) {
    ev.preventDefault();
    if (!Quote.items.length) return;
    var f = $(".quote-form", drawer);
    var nombre = cleanInput(f.elements.nombre.value, 80);
    var empresa = cleanInput(f.elements.empresa.value, 80);
    var ciudad = cleanInput(f.elements.ciudad.value, 60);
    var notas = cleanInput(f.elements.notas.value, 500);
    var lines = ["Hola RUAV, me gustaría solicitar una cotización de los siguientes productos:", ""];
    Quote.items.forEach(function (it) { lines.push(lineFor(BY_SKU.get(it.sku), it.qty, it.opcion)); });    lines.push("");
    if (nombre) lines.push("Nombre: " + nombre);
    if (empresa) lines.push("Empresa: " + empresa);
    if (ciudad) lines.push("Ciudad de entrega: " + ciudad);
    if (notas) lines.push("Comentarios: " + notas);
    window.open(waLink(lines.join("\n")), "_blank", "noopener,noreferrer");
  }

  function initDrawer() {
    drawer = $("#cotizacion");
    backdrop = $("#quote-backdrop");
    if (!drawer) return;
    $all("[data-open-quote]").forEach(function (b) { b.addEventListener("click", openDrawer); });
    $all("[data-close-quote]").forEach(function (b) { b.addEventListener("click", closeDrawer); });
    backdrop.addEventListener("click", closeDrawer);
    $(".quote-form", drawer).addEventListener("submit", sendQuote);
    $("[data-clear-quote]", drawer).addEventListener("click", function () {
      if (window.confirm("¿Vaciar tu lista de cotización?")) { Quote.items = []; Quote.save(); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeDrawer(); closeFilters(); closeMenu(); closeMega(); }
      if (e.key === "Tab" && drawer.classList.contains("open")) trapFocus(e, drawer);
    });
  }
  function trapFocus(e, root) {
    var f = $all("a[href], button:not([disabled]), input, textarea, select", root).filter(function (el) { return el.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ---------------- Aviso emergente ---------------- */

  var toastEl, toastTimer;
  function toast(msg, withAction) {
    if (!toastEl) {
      toastEl = h("div", { class: "toast", role: "status", "aria-live": "polite" });
      document.body.appendChild(toastEl);
    }
    clear(toastEl);
    toastEl.appendChild(h("span", { text: msg }));
    if (withAction) toastEl.appendChild(h("button", { type: "button", text: "Ver cotización", onclick: function () { toastEl.classList.remove("show"); openDrawer(); } }));
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove("show"); }, 3800);
  }

  /* ---------------- Tarjeta de producto ---------------- */

  function syncAddButton(btn) {
    var inQuote = Quote.has(btn.getAttribute("data-add-sku"));
    btn.classList.toggle("added", inQuote);
    var label = $(".label", btn);
    if (label) label.textContent = inQuote ? (btn.getAttribute("data-added") || "Agregado") : (btn.getAttribute("data-label") || "Agregar");
  }
  function addButton(p, opts) {
    opts = opts || {};
    var btn = h("button", {
      type: "button", class: opts.cls || "btn btn-outline btn-add", "data-add-sku": p.sku, "data-label": opts.label || "Agregar", "data-added": opts.added || "Agregado",
      onclick: function () {
        var opcion = opts.opcion ? opts.opcion() : "";
        if (Quote.add(p.sku, opts.qty ? opts.qty() : 1, opcion)) {
          toast(p.nombre + (opcion ? " (" + opcion + ")" : "") + " agregado a tu cotización", true);
        }
      },
    }, h("span", { class: "label" }));
    syncAddButton(btn);
    return btn;
  }
  function productCard(p, showCat) {
    var cat = CAT_BY_ID.get(p.cat);
    return h("article", { class: "product-card" },
      h("div", { class: isSilla(p) ? "pc-img pc-photo" : "pc-img" }, img(p), showCat && cat ? h("span", { class: "pc-tag", text: cat.name }) : h("span", { class: "pc-tag", text: p.tipo })),
      h("div", { class: "pc-body" },
        h("span", { class: "pc-sku", text: subtitle(p) }),
        h("h3", { class: "pc-title" }, h("a", { href: productUrl(p), text: p.nombre })),
        p.medidas ? h("dl", { class: "pc-dims" }, dimLabels(p).map(function (d) {
          return h("div", null, h("dt", { text: d[0] }), h("dd", { text: fmtLen(d[1]) }));
        })) : null,
        isSilla(p) && p.caracteristicas.length ? h("p", { class: "pc-feat", text: p.caracteristicas[0] }) : null,
        isSilla(p) && p.desde ? h("p", { class: "pc-price" }, h("small", { text: (priceOptions(p).length > 1 ? "Desde" : "Precio de lista") + (p.iva ? " · más IVA" : "") }),
          money(p.desde), h("sup", { text: "*", title: avisoFor(p) })) : null,
        h("div", { class: "pc-actions" },
          addButton(p),
          waAnchor(singleMessage(p, 1), "Cotizar " + p.nombre + " por WhatsApp", "btn btn-wa icon-only"))));
  }

  /* ---------------- Encabezado y navegación ---------------- */

  var nav, menuBtn, drop;
  function closeMenu() {
    if (!nav || !nav.classList.contains("open")) return;
    nav.classList.remove("open");
    menuBtn.setAttribute("aria-expanded", "false");
    menuBtn.setAttribute("aria-label", "Abrir menú");
    $("use", menuBtn).setAttribute("href", ICONS + "menu");
    document.body.classList.remove("no-scroll");
  }
  function closeMega() {
    if (drop && drop.classList.contains("open")) {
      drop.classList.remove("open");
      $("button", drop).setAttribute("aria-expanded", "false");
    }
  }
  function initHeader() {
    nav = $("#nav");
    menuBtn = $(".menu-toggle");
    drop = $(".nav-drop");
    if (menuBtn && nav) {
      menuBtn.addEventListener("click", function () {
        var open = !nav.classList.contains("open");
        if (!open) return closeMenu();
        var hdr = $(".site-header").getBoundingClientRect();
        nav.style.top = Math.max(0, Math.round(hdr.bottom)) + "px";
        nav.classList.add("open");
        menuBtn.setAttribute("aria-expanded", "true");
        menuBtn.setAttribute("aria-label", "Cerrar menú");
        $("use", menuBtn).setAttribute("href", ICONS + "close");
        document.body.classList.add("no-scroll");
      });
    }
    if (drop) {
      var mega = $(".mega", drop);
      GRUPOS.forEach(function (g) {
        mega.appendChild(h("a", { class: "mega-group", href: catalogUrl({ grupo: g.id }) }, g.name, icon("arrow")));
        CATS.filter(function (c) { return c.grupo === g.id; }).forEach(function (c) {
          var first = coverOf(c);
          mega.appendChild(h("a", { href: catalogUrl({ cat: c.id }) },
            first ? img(first) : null,
            h("span", null, h("strong", { text: c.name }), h("small", { text: c.count + " modelos" }))));
        });
      });
      mega.appendChild(h("a", { class: "mega-all", href: "catalogo.html", text: "Ver todo el catálogo (" + PRODUCTS.length + " productos)" }));
      var btn = $("button", drop);
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = !drop.classList.contains("open");
        drop.classList.toggle("open", open);
        btn.setAttribute("aria-expanded", String(open));
      });
      document.addEventListener("click", function (e) { if (!drop.contains(e.target)) closeMega(); });
    }
  }

  // Datos de contacto desde config.js
  function initContactInfo() {
    $all("[data-wa-general]").forEach(function (a) {
      a.href = waLink(generalMessage());
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    });
    var map = {
      telefono: function (v) { return "tel:+52" + v.replace(/\D/g, "").slice(-10); },
      email: function (v) { return /^[^\s@<>"]+@[^\s@<>"]+\.[a-z]{2,}$/i.test(v) ? "mailto:" + v : null; },
      direccion: function () { return null; },
      horario: function () { return null; },
    };
    Object.keys(map).forEach(function (key) {
      var v = cleanInput(CFG[key], 160);
      $all("[data-cfg='" + key + "']").forEach(function (el) {
        var row = el.closest("[data-cfg-row]");
        if (!v) { if (row) row.hidden = true; return; }
        el.textContent = v;
        var href = map[key](v);
        if (href && el.tagName === "A") el.href = href;
      });
    });
    $all("[data-year]").forEach(function (el) { el.textContent = String(new Date().getFullYear()); });
  }

  /* ---------------- Página: inicio ---------------- */

  function initHome() {
    $all("[data-cat-grid]").forEach(function (grid) {
      var grupo = grid.getAttribute("data-cat-grid");
      CATS.filter(function (c) { return c.grupo === grupo; }).forEach(function (c) {
        var first = coverOf(c);
        grid.appendChild(h("a", { class: "cat-card", href: catalogUrl({ cat: c.id }) },
          h("div", { class: "cat-img" }, first ? img(first) : null),
          h("strong", { text: c.name }),
          h("span", { text: c.count + " modelos" })));
      });
    });
    $all("[data-stat='productos']").forEach(function (el) { el.textContent = String(PRODUCTS.length); });
    $all("[data-stat='categorias']").forEach(function (el) { el.textContent = String(CATS.length); });

    var tabs = $("#featured-tabs"), out = $("#featured-grid");
    if (!tabs || !out) return;
    var picks = ["escritorios", "sillas-oficina", "mesas-asamblea", "credenzas", "sillones-lounge", "almacenamiento", "lockers", "barras-altas"];
    function featured(catId) {
      var seen = new Set();
      return PRODUCTS.filter(function (p) {
        var key = p.familia || p.nombre;
        if (p.cat !== catId || seen.has(key)) return false;
        seen.add(key);
        return true;
      }).concat(PRODUCTS.filter(function (p) { return p.cat === catId; })).filter(function (p, i, arr) {
        return arr.indexOf(p) === i;
      }).slice(0, 8);
    }
    function show(catId, btn) {
      $all(".tab", tabs).forEach(function (t) { t.setAttribute("aria-selected", String(t === btn)); t.tabIndex = t === btn ? 0 : -1; });
      clear(out);
      featured(catId).forEach(function (p) { out.appendChild(productCard(p)); });
      var more = $("#featured-more");
      if (more) { more.href = catalogUrl({ cat: catId }); $(".label", more).textContent = "Ver todo en " + CAT_BY_ID.get(catId).name; }
    }
    picks.forEach(function (id, i) {
      var c = CAT_BY_ID.get(id);
      if (!c) return;
      var b = h("button", { type: "button", class: "tab", role: "tab", id: "tab-" + id, "aria-controls": "featured-grid", text: c.name,
        onclick: function () { show(id, b); } });
      b.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var all = $all(".tab", tabs), idx = all.indexOf(b) + (e.key === "ArrowRight" ? 1 : -1);
        var next = all[(idx + all.length) % all.length];
        next.focus(); next.click();
      });
      tabs.appendChild(b);
      if (i === 0) show(id, b);
    });
  }

  /* ---------------- Página: catálogo ---------------- */

  var filtersEl, filtersBackdrop;
  function closeFilters() {
    if (!filtersEl || !filtersEl.classList.contains("open")) return;
    filtersEl.classList.remove("open");
    document.body.classList.remove("no-scroll");
    if (filtersBackdrop) { filtersBackdrop.classList.remove("show"); setTimeout(function () { filtersBackdrop.hidden = true; }, 250); }
  }

  function initCatalog() {
    var grid = $("#catalog-grid");
    if (!grid) return;
    filtersEl = $("#filters");
    filtersBackdrop = $(".filters-backdrop");
    var PAGE = 24;
    var params = new URLSearchParams(location.search);
    var state = {
      cat: CAT_BY_ID.has(params.get("cat")) ? params.get("cat") : "",
      grupo: GRUPO_BY_ID.has(params.get("grupo")) ? params.get("grupo") : "",
      tipos: (params.get("tipo") || "").split("|").map(function (t) { return cleanInput(t, 60); }).filter(Boolean),
      frente: /^\d{2,5}$/.test(params.get("frente") || "") ? params.get("frente") : "",
      fondo: /^\d{2,5}$/.test(params.get("fondo") || "") ? params.get("fondo") : "",
      alto: /^\d{2,5}$/.test(params.get("alto") || "") ? params.get("alto") : "",
      q: cleanInput(params.get("q"), 80),
      orden: ["", "frente-asc", "frente-desc", "precio-asc", "precio-desc", "nombre", "clave"].indexOf(params.get("orden")) > 0 ? params.get("orden") : "",
      shown: PAGE,
    };

    var qInput = $("#q-inline"), sortSel = $("#orden");
    qInput.value = state.q;
    sortSel.value = state.orden;
    var headerQ = $(".header-search input");
    if (headerQ) headerQ.value = state.q;

    function inCat() {
      if (state.cat) return PRODUCTS.filter(function (p) { return p.cat === state.cat; });
      if (state.grupo) return PRODUCTS.filter(function (p) { return CAT_BY_ID.get(p.cat).grupo === state.grupo; });
      return PRODUCTS;
    }
    function matches(p) {
      if (state.tipos.length && state.tipos.indexOf(p.tipo) === -1) return false;
      if (state.frente && (!p.medidas || String(p.medidas.frente) !== state.frente)) return false;
      if (state.fondo && (!p.medidas || String(p.medidas.fondo) !== state.fondo)) return false;
      if (state.alto && (!p.medidas || String(p.medidas.alto) !== state.alto)) return false;
      if (state.q) {
        var cat = CAT_BY_ID.get(p.cat);
        var hay = normalize([p.nombre, p.sku, p.tipo, p.descripcion, cat ? cat.name : "", dimsShort(p),
          (p.tapices || []).join(" "), (p.versiones || []).join(" "), p.clave || ""].join(" "));
        var ok = normalize(state.q).split(/\s+/).every(function (t) { return hay.indexOf(t) > -1; });
        if (!ok) return false;
      }
      return true;
    }
    function sortList(list) {
      var s = state.orden;
      if (!s) return list;
      var copy = list.slice();
      if (s === "clave") copy.sort(function (a, b) { return a.sku.localeCompare(b.sku); });
      else if (s === "nombre") copy.sort(function (a, b) { return a.nombre.localeCompare(b.nombre, "es"); });
      else if (s === "precio-asc" || s === "precio-desc") copy.sort(function (a, b) {
        // Los productos sin precio publicado (mobiliario) van al final.
        if (!a.desde || !b.desde) return (a.desde ? 0 : 1) - (b.desde ? 0 : 1);
        return s === "precio-asc" ? a.desde - b.desde : b.desde - a.desde;
      });
      else copy.sort(function (a, b) {
        var d = ((a.medidas || {}).frente || 0) - ((b.medidas || {}).frente || 0);
        if (!d) d = ((a.medidas || {}).fondo || 0) - ((b.medidas || {}).fondo || 0);
        return s === "frente-desc" ? -d : d;
      });
      return copy;
    }

    function syncUrl() {
      var p = new URLSearchParams();
      if (state.cat) p.set("cat", state.cat);
      else if (state.grupo) p.set("grupo", state.grupo);
      if (state.tipos.length) p.set("tipo", state.tipos.join("|"));
      ["frente", "fondo", "alto", "q", "orden"].forEach(function (k) { if (state[k]) p.set(k, state[k]); });
      var qs = p.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
    }

    function radio(name, value, label, count, checked, onChange, cls) {
      return h("li", { class: cls }, h("label", null,
        h("input", { type: name === "tipo" ? "checkbox" : "radio", name: name, value: value, checked: checked, onchange: onChange }),
        h("span", { text: label }), h("span", { class: "count", text: String(count) })));
    }

    function renderFilters() {
      var catList = $("#f-cat");
      clear(catList);
      catList.appendChild(radio("cat", "", "Todo el catálogo", PRODUCTS.length, !state.cat && !state.grupo, function () { setCat("", ""); }));
      GRUPOS.forEach(function (g) {
        var cats = CATS.filter(function (c) { return c.grupo === g.id; });
        var total = cats.reduce(function (a, c) { return a + c.count; }, 0);
        catList.appendChild(radio("cat", "grupo:" + g.id, g.name, total, !state.cat && state.grupo === g.id,
          function () { setCat("", g.id); }, "filter-group-head"));
        cats.forEach(function (c) {
          catList.appendChild(radio("cat", c.id, c.name, c.count, state.cat === c.id, function () { setCat(c.id); }, "filter-sub"));
        });
      });

      var base = inCat();
      var tipoGroup = $("#g-tipo"), tipoList = $("#f-tipo");
      var tipos = [];
      base.forEach(function (p) { if (tipos.indexOf(p.tipo) === -1) tipos.push(p.tipo); });
      state.tipos = state.tipos.filter(function (t) { return tipos.indexOf(t) > -1; });
      tipoGroup.hidden = !state.cat || tipos.length < 2;
      clear(tipoList);
      tipos.forEach(function (t) {
        var n = base.filter(function (p) { return p.tipo === t; }).length;
        tipoList.appendChild(radio("tipo", t, t, n, state.tipos.indexOf(t) > -1, function (e) {
          if (e.target.checked) state.tipos.push(t);
          else state.tipos = state.tipos.filter(function (x) { return x !== t; });
          update();
        }));
      });

      ["frente", "fondo", "alto"].forEach(function (k) {
        var sel = $("#f-" + k);
        var vals = [];
        base.forEach(function (p) { if (p.medidas && vals.indexOf(p.medidas[k]) === -1) vals.push(p.medidas[k]); });
        vals.sort(function (a, b) { return a - b; });
        if (state[k] && vals.indexOf(+state[k]) === -1) state[k] = "";
        clear(sel);
        sel.appendChild(h("option", { value: "", text: "Todas" }));
        vals.forEach(function (v) { sel.appendChild(h("option", { value: String(v), text: fmtLen(v), selected: String(v) === state[k] })); });
      });
      $("#g-medidas").hidden = !base.some(function (p) { return p.medidas; });
      var altoLabel = $("#l-alto");
      if (altoLabel) altoLabel.textContent = state.cat === "cubiertas" ? "Grosor" : "Alto";
    }

    function setCat(id, grupo) {
      state.cat = id;
      state.grupo = id ? CAT_BY_ID.get(id).grupo : (grupo || "");
      state.tipos = [];
      state.frente = state.fondo = state.alto = "";
      update(true);
    }

    function renderHead() {
      var c = CAT_BY_ID.get(state.cat) || GRUPO_BY_ID.get(state.grupo);
      $("#cat-title").textContent = c ? c.name : "Catálogo";
      $("#cat-blurb").textContent = c ? c.blurb : "Mobiliario de oficina y sillería: escritorios, mesas de juntas, credenzas, almacenamiento, lockers, sillas, sillones y sofás. Agrega productos a tu lista y envía tu cotización por WhatsApp.";
      var crumb = $("#crumb-cat");
      crumb.hidden = !c;
      crumb.textContent = c ? c.name : "";
      document.title = (c ? c.name + " | " : "Catálogo | ") + "RUAV Mobiliario";
    }

    function renderActive() {
      var box = $("#active-filters");
      clear(box);
      function pill(label, fn) {
        box.appendChild(h("button", { type: "button", "aria-label": "Quitar filtro " + label, onclick: fn }, label, icon("close")));
      }
      if (state.q) pill("“" + state.q + "”", function () { state.q = ""; qInput.value = ""; update(); });
      state.tipos.forEach(function (t) { pill(t, function () { state.tipos = state.tipos.filter(function (x) { return x !== t; }); update(); }); });
      [["frente", "Frente"], ["fondo", "Fondo"], ["alto", state.cat === "cubiertas" ? "Grosor" : "Alto"]].forEach(function (k) {
        if (state[k[0]]) pill(k[1] + ": " + fmtLen(+state[k[0]]), function () { state[k[0]] = ""; update(); });
      });
      box.hidden = !box.firstChild;
      $all(".active-filters svg").forEach(function (s) { s.setAttribute("width", "14"); s.setAttribute("height", "14"); });
    }

    function renderGrid() {
      var list = sortList(inCat().filter(matches));
      $("#results-count").textContent = String(list.length);
      $("#results-noun").textContent = list.length === 1 ? " producto" : " productos";
      clear(grid);
      $("#catalog-empty").hidden = list.length > 0;
      var notice = $("#price-notice");
      if (notice) {
        notice.textContent = "* " + AVISO_PRECIOS;
        notice.hidden = !list.some(function (p) { return p.desde; });
      }
      list.slice(0, state.shown).forEach(function (p) { grid.appendChild(productCard(p, !state.cat)); });
      var more = $("#load-more");
      more.hidden = list.length <= state.shown;
      $(".label", more).textContent = "Ver más productos (" + (list.length - Math.min(state.shown, list.length)) + " restantes)";
    }

    function update(resetPage) {
      if (resetPage !== false) state.shown = PAGE;
      renderFilters();
      renderHead();
      renderActive();
      renderGrid();
      syncUrl();
    }

    ["frente", "fondo", "alto"].forEach(function (k) {
      $("#f-" + k).addEventListener("change", function (e) { state[k] = /^\d{2,5}$/.test(e.target.value) ? e.target.value : ""; update(); });
    });
    var qTimer;
    qInput.addEventListener("input", function () {
      clearTimeout(qTimer);
      qTimer = setTimeout(function () { state.q = cleanInput(qInput.value, 80); update(); }, 180);
    });
    $("#q-form").addEventListener("submit", function (e) { e.preventDefault(); state.q = cleanInput(qInput.value, 80); update(); });
    sortSel.addEventListener("change", function () { state.orden = sortSel.value; update(); });
    $("#load-more").addEventListener("click", function () { state.shown += PAGE; renderGrid(); });
    $all("[data-clear-filters]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.tipos = []; state.frente = state.fondo = state.alto = state.q = ""; qInput.value = "";
        update();
      });
    });
    $("#filters-open").addEventListener("click", function () {
      filtersEl.classList.add("open");
      document.body.classList.add("no-scroll");
      filtersBackdrop.hidden = false;
      requestAnimationFrame(function () { filtersBackdrop.classList.add("show"); });
    });
    $all("[data-close-filters]").forEach(function (b) { b.addEventListener("click", closeFilters); });
    filtersBackdrop.addEventListener("click", closeFilters);

    update();
  }

  /* ---------------- Acabados ---------------- */

  function swatch(a, opts) {
    opts = opts || {};
    return h(opts.tag || "div", Object.assign({ class: "swatch", title: a.nombre }, opts.attrs || {}),
      h("img", { src: "assets/img/acabados/" + a.id + ".webp", alt: "", width: 240, height: 240, loading: "lazy", decoding: "async" }),
      h("span", { text: a.nombre }));
  }
  function finishGroups() {
    var groups = [];
    ACABADOS.forEach(function (a) {
      var g = groups.find(function (x) { return x.tipo === a.tipo; });
      if (!g) groups.push(g = { tipo: a.tipo, items: [] });
      g.items.push(a);
    });
    return groups;
  }
  function finishSrc(a) { return "assets/img/acabados/" + a.id + ".webp"; }

  // Visor ampliado de acabados (con flechas para recorrerlos). onPick opcional: botón "Elegir este acabado".
  var viewer;
  function openFinishViewer(nombre, onPick) {
    if (!viewer) {
      var big = h("img", { alt: "", width: 272, height: 272 });
      var title = h("h2"), kind = h("small"), count = h("span", { class: "fv-count" });
      var pickBtn = h("button", { type: "button", class: "btn btn-dark btn-sm", text: "Elegir este acabado" });
      var dlg = h("dialog", { class: "finish-viewer", "aria-label": "Acabado ampliado" },
        h("button", { type: "button", class: "icon-btn fv-close", "aria-label": "Cerrar", onclick: function () { dlg.close(); } }, icon("close")),
        h("div", { class: "fv-stage" },
          h("button", { type: "button", class: "icon-btn fv-nav fv-prev", "aria-label": "Acabado anterior", onclick: function () { viewer.go(-1); } }, icon("arrow")),
          big,
          h("button", { type: "button", class: "icon-btn fv-nav fv-next", "aria-label": "Acabado siguiente", onclick: function () { viewer.go(1); } }, icon("arrow"))),
        h("div", { class: "fv-info" }, kind, title, count),
        pickBtn,
        h("p", { class: "stock-note", text: AVISO_EXISTENCIAS }));
      dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); }); // clic en el fondo
      dlg.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") viewer.go(1);
        if (e.key === "ArrowLeft") viewer.go(-1);
      });
      document.body.appendChild(dlg);
      viewer = {
        dlg: dlg, i: 0, onPick: null,
        show: function (i) {
          this.i = (i + ACABADOS.length) % ACABADOS.length;
          var a = ACABADOS[this.i];
          big.src = finishSrc(a);
          big.alt = "Acabado " + a.nombre;
          title.textContent = a.nombre;
          kind.textContent = a.tipo;
          count.textContent = (this.i + 1) + " de " + ACABADOS.length;
        },
        go: function (d) { this.show(this.i + d); },
      };
      pickBtn.addEventListener("click", function () {
        if (viewer.onPick) viewer.onPick(ACABADOS[viewer.i].nombre);
        dlg.close();
      });
      viewer.pickBtn = pickBtn;
    }
    viewer.onPick = onPick || null;
    viewer.pickBtn.hidden = !onPick;
    viewer.show(Math.max(0, ACABADOS.findIndex(function (a) { return a.nombre === nombre; })));
    if (typeof viewer.dlg.showModal === "function") viewer.dlg.showModal();
    else viewer.dlg.setAttribute("open", "");
  }

  // Selector de acabado en la ficha de mobiliario: vista previa grande + muestras; clic de nuevo quita la selección.
  function finishPicker(onChange) {
    var current = "";
    var label = h("strong", { text: "Sin elegir (opcional)" });
    var prevImg = h("img", { alt: "", width: 272, height: 272 });
    var prevName = h("strong"), prevKind = h("small");
    var preview = h("div", { class: "finish-preview", hidden: true },
      h("button", { type: "button", class: "fp-img", "aria-label": "Ver acabado en grande", onclick: function () {
        openFinishViewer(preview.getAttribute("data-nombre"), function (n) { if (n !== current) select(n); });
      } }, prevImg),
      h("div", null, prevKind, prevName,
        h("button", { type: "button", class: "link-btn", text: "Ver en grande", onclick: function () {
          openFinishViewer(preview.getAttribute("data-nombre"), function (n) { if (n !== current) select(n); });
        } })));
    var buttons = [];
    function showPreview(nombre) {
      var a = ACAB_BY_NAME.get(nombre);
      preview.hidden = !a;
      if (!a) return;
      preview.setAttribute("data-nombre", a.nombre);
      prevImg.src = finishSrc(a);
      prevImg.alt = "Acabado " + a.nombre;
      prevName.textContent = a.nombre;
      prevKind.textContent = a.tipo;
    }
    function select(nombre) {
      current = current === nombre ? "" : nombre;
      buttons.forEach(function (b) { b.setAttribute("aria-checked", String(b.getAttribute("data-nombre") === current)); });
      label.textContent = current || "Sin elegir (opcional)";
      showPreview(current);
      onChange(current);
    }
    var block = h("div", { class: "finish-picker" },
      h("div", { class: "finish-head" }, h("span", { text: "Acabado: " }), label),
      preview,
      finishGroups().map(function (g) {
        return h("div", { class: "finish-group" },
          h("small", { text: g.tipo }),
          h("div", { class: "swatches", role: "radiogroup", "aria-label": "Acabados " + g.tipo }, g.items.map(function (a) {
            var b = swatch(a, { tag: "button", attrs: { type: "button", role: "radio", "aria-checked": "false", "data-nombre": a.nombre,
              "aria-label": a.nombre, onclick: function () { select(a.nombre); },
              onmouseenter: function () { showPreview(a.nombre); },
              onmouseleave: function () { showPreview(current); },
              onfocus: function () { showPreview(a.nombre); },
              onblur: function () { showPreview(current); } } });
            buttons.push(b);
            return b;
          })));
      }),
      h("p", { class: "stock-note", text: AVISO_EXISTENCIAS }));
    return block;
  }
  function initFinishGallery() {
    var root = $("#acabados-grid");
    if (!root) return;
    finishGroups().forEach(function (g) {
      root.appendChild(h("div", { class: "finish-group" },
        h("h3", { text: g.tipo + " (" + g.items.length + ")" }),
        h("div", { class: "swatches swatches-lg" }, g.items.map(function (a) {
          return swatch(a, { tag: "button", attrs: { type: "button", "aria-label": "Ver " + a.nombre + " en grande",
            onclick: function () { openFinishViewer(a.nombre); } } });
        }))));
    });
  }

  /* ---------------- Página: producto ---------------- */

  function initProduct() {
    var root = $("#product-root");
    if (!root) return;
    var sku = (new URLSearchParams(location.search).get("sku") || "").toUpperCase();
    var p = SKU_RE.test(sku) ? BY_SKU.get(sku) : null;
    if (!p) {
      $("#product-missing").hidden = false;
      document.title = "Producto no encontrado | RUAV Mobiliario";
      return;
    }
    var cat = CAT_BY_ID.get(p.cat);
    document.title = (p.nombre + " " + dimsShort(p)).trim() + " | RUAV Mobiliario";
    var canonical = (/^https:\/\/[^\s"'<>]+$/.test(CFG.sitioUrl || "") ? CFG.sitioUrl.replace(/\/$/, "") : location.origin) + "/" + productUrl(p);
    document.head.appendChild(h("link", { rel: "canonical", href: canonical }));
    var meta = $("meta[name='description']");
    if (meta) meta.setAttribute("content", p.descripcion.slice(0, 155));
    var catLink = $("#crumb-cat");
    catLink.textContent = cat.name;
    catLink.href = catalogUrl({ cat: cat.id });
    $("#crumb-product").textContent = p.nombre;

    var silla = isSilla(p);
    var variants = silla
      ? PRODUCTS.filter(function (x) { return x.familia === p.familia && (x.linea || "") === (p.linea || ""); })
      : PRODUCTS.filter(function (x) { return x.cat === p.cat && x.nombre === p.nombre; }).sort(function (a, b) {
        var A = a.medidas || {}, B = b.medidas || {};
        return (A.fondo - B.fondo) || (A.frente - B.frente) || (A.alto - B.alto) || 0;
      });
    function variantLabel(v) {
      if (!silla) return v.medidas ? [v.medidas.frente, v.medidas.fondo, v.medidas.alto].map(function (n) { return n < 100 ? n + "mm" : (n / 1000).toFixed(2); }).join(" × ") : v.sku;
      if (v.nombre.indexOf(p.familia) !== 0) return v.nombre;   // nombres que no empiezan con la familia
      var rest = v.nombre.slice(p.familia.length).replace(/^[\s·-]+/, "");
      return rest || "Estándar";
    }
    var qtyVal = 1, optVal = "";
    var waBtn = waAnchor(singleMessage(p, 1), "Cotizar por WhatsApp", "btn btn-wa btn-block");
    function refreshWa() { waBtn.href = waLink(singleMessage(p, qtyVal, optVal)); }
    var qty = qtyControl(1, function (v) { qtyVal = v; refreshWa(); });
    var tapizSelect = null;
    if (silla && priceOptions(p).length) {
      var opts = priceOptions(p);
      var single = opts.length === 1;
      var iva = p.iva ? " · más IVA" : "";
      var priceLabel = h("small", { text: (single ? "Precio de lista" : "Desde") + iva });
      var priceValue = h("strong", { text: money(single ? opts[0].precio : p.desde) });
      tapizSelect = h("div", { class: "price-box" },
        h("div", { class: "price-now" }, priceLabel, priceValue),
        single ? (opts[0].opcion !== "Precio sugerido" ? h("p", { class: "price-opt", text: opts[0].opcion }) : null) : h("label", { class: "tapiz-select" }, "Elige tapicería o versión para ver su precio",
          h("select", { class: "field", onchange: function (e) {
            optVal = validOption(p, e.target.value) ? e.target.value : "";
            priceLabel.textContent = (optVal ? "Precio de lista" : "Desde") + iva;
            priceValue.textContent = money(optVal ? priceOf(p, optVal) : p.desde);
            refreshWa();
          } },
            h("option", { value: "", text: "Selecciona una opción" }),
            opts.map(function (o) { return h("option", { value: o.opcion, text: o.opcion + " — " + money(o.precio) }); }))),
        extrasOf(p).map(function (x) { return h("p", { class: "price-extra", text: x.opcion.replace(" (adicional)", "") + ": +" + money(x.precio) + " (adicional)" }); }),
        h("p", { class: "price-note", text: avisoFor(p) }));
    }
    var acabadoPicker = !silla && ACABADOS.length ? finishPicker(function (nombre) { optVal = nombre; refreshWa(); }) : null;
    refreshWa();

    var features = silla ? p.caracteristicas.slice() : [];
    var d = silla ? "" : normalize(p.descripcion);
    if (d.indexOf("blum") > -1) features.push("Bisagras bidimensionales BLUM de cierre suave");
    // Solo los escritorios y barras tipo grapa son desarmables.
    if (p.cat === "escritorios" || p.cat === "barras-altas") features.push("100 % desarmable: fácil de transportar e instalar");
    if (d.indexOf("cerradura") > -1) features.push("Incluye cerradura");
    if (d.indexOf("extension total") > -1) features.push("Correderas de extensión total");
    if (d.indexOf("nivelador") > -1) features.push("Niveladores para pisos irregulares");
    if (d.indexOf("cableado") > -1) features.push("Paso de cableado integrado");
    if (d.indexOf("rodajas") > -1) features.push("Rodajas para moverlo con facilidad");
    var panel = d.match(/panel[^.]*?(\d{2}) mm/);
    if (panel) features.push("Panel melamínico de " + panel[1] + " mm");

    var product = h("div", { class: "product" },
      h("div", { class: "product-media" }, img(p, null, true), h("span", { class: "pc-tag", text: p.tipo }),
        p.imgRef ? h("span", { class: "img-ref", text: "Imagen de referencia: el modelo puede variar en material o detalles" }) : null),
      h("div", { class: "product-info" },
        h("span", { class: "eyebrow", text: cat.name }),
        h("h1", { text: p.nombre }),
        silla ? h("div", { class: "pc-sku", text: (p.clave ? "Clave: " + p.clave + " · " : "") + p.tipo }) : h("div", { class: "pc-sku" }, "Clave: " + p.sku,
          h("button", { type: "button", class: "copy-btn", text: "Copiar", onclick: function (e) {
            var b = e.currentTarget;
            if (navigator.clipboard) navigator.clipboard.writeText(p.sku).then(function () { b.textContent = "Copiada"; }, function () {});
          } })),
        p.medidas ? h("div", { class: "dims-table" }, dimLabels(p).map(function (x) {
          var parts = fmtLen(x[1]).split(" ");
          return h("div", null, h("small", { text: x[0] }), h("strong", null, parts[0], h("span", { text: parts[1] })));
        })) : null,
        variants.length > 1 ? h("div", { class: "variant-block" },
          h("h2", { text: (silla ? "Versiones de " + p.familia : "Medidas disponibles") + " (" + variants.length + ")" }),
          h("div", { class: "variants" }, variants.map(function (v) {
            return h("a", { href: productUrl(v), "aria-current": v.sku === p.sku ? "true" : null, text: variantLabel(v) });
          }))) : null,
        h("div", { class: "buy-box" },
          tapizSelect,
          acabadoPicker,
          h("div", { class: "buy-row" }, qty, addButton(p, { cls: "btn btn-dark btn-add", label: "Agregar a cotización", added: "Agregar más",
            qty: function () { return qtyVal; }, opcion: function () { return optVal; } })),
          waBtn,
          h("p", { class: "buy-note" }, icon("wa"), silla
            ? "Te respondemos por WhatsApp para confirmar precio final, existencias, muestrario de tapices y tiempo de entrega."
            : "Te respondemos por WhatsApp con precio, existencias y tiempo de entrega.")),
        h("div", { class: "spec" },
          silla && !(p.descripcion && p.descripcion !== p.nombre) ? null : h("h2", { text: "Descripción" }),
          silla && !(p.descripcion && p.descripcion !== p.nombre) ? null : h("p", { text: p.descripcion }),
          (p.dimensiones || []).length ? h("h2", { text: "Medidas" }) : null,
          (p.dimensiones || []).length ? h("ul", null, p.dimensiones.map(function (f) { return h("li", { text: f }); })) : null,
          features.length ? h("h2", { text: "Características" }) : null,
          features.length ? h("ul", null, features.map(function (f) { return h("li", { text: f }); })) : null,
          silla && p.versiones.length ? h("h2", { text: "Opciones" }) : null,
          silla && p.versiones.length ? h("ul", null, p.versiones.map(function (f) { return h("li", { text: f }); })) : null,
          silla && (p.precios || []).length > 1 ? h("h2", { text: "Precios de lista por tapicería" }) : null,
          silla && (p.precios || []).length > 1 ? h("table", { class: "price-table" },
            h("tbody", null, p.precios.map(function (x) {
              return h("tr", null, h("td", { text: x.opcion }), h("td", { text: (x.opcion.indexOf("(adicional)") > -1 ? "+" : "") + money(x.precio) }));
            }))) : null,
          silla && (p.precios || []).length > 1 ? h("p", { class: "price-note", text: avisoFor(p) }) : null)));
    root.appendChild(product);

    var groupKey = function (x) { return x.familia || x.nombre; };
    var related = PRODUCTS.filter(function (x) { return x.cat === p.cat && groupKey(x) !== groupKey(p); });
    var seen = new Set();
    related = related.filter(function (x) { if (seen.has(groupKey(x))) return false; seen.add(groupKey(x)); return true; }).slice(0, 4);
    if (related.length < 4) {
      related = related.concat(PRODUCTS.filter(function (x) { return x.cat !== p.cat && x.sku === PRODUCTS.find(function (y) { return y.cat === x.cat; }).sku; }).slice(0, 4 - related.length));
    }
    var relGrid = $("#related-grid");
    related.forEach(function (x) { relGrid.appendChild(productCard(x)); });
    $("#related").hidden = false;
    var relMore = $("#related-more");
    relMore.href = catalogUrl({ cat: cat.id });
    $(".label", relMore).textContent = "Ver todo en " + cat.name;
  }

  /* ---------------- Inicio ---------------- */

  function init() {
    Quote.load();
    initHeader();
    initDrawer();
    initContactInfo();
    initHome();
    initFinishGallery();
    initCatalog();
    initProduct();
    renderQuote();
    // Si otra pestaña modifica la cotización, sincronizar.
    window.addEventListener("storage", function (e) { if (e.key === STORE_KEY) { Quote.load(); renderQuote(); } });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
