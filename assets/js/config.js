/*
 * Configuración del negocio. Este es el ÚNICO archivo que hay que editar
 * para cambiar los datos de contacto que aparecen en todo el sitio.
 */
window.RUAV_CONFIG = Object.freeze({
  // Número de WhatsApp en formato internacional, solo dígitos (México: 52 + 10 dígitos).
  // Ejemplo: "5215512345678" o "525512345678". Si se deja vacío, WhatsApp pedirá elegir el contacto.
  whatsapp: "",

  // Datos visibles en el sitio (dejar "" para ocultar la línea correspondiente).
  telefono: "",            // Ej. "55 1234 5678"
  email: "",               // Ej. "ventas@ruav.com.mx"
  direccion: "",           // Ej. "Av. Ejemplo 123, Col. Centro, CDMX"
  horario: "Lunes a viernes de 9:00 a 18:00 h",

  // URL pública del sitio (se usa en los enlaces que van dentro de los mensajes de WhatsApp).
  // En el ambiente de stage, el workflow la reemplaza automáticamente.
  sitioUrl: "https://ruav.com.mx",
});
