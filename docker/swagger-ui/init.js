// Served from a file because `script-src 'self'` blocks the inline bootstrap FastAPI emits.
(function () {
  var el = document.getElementById("swagger-ui");
  if (!el || typeof SwaggerUIBundle === "undefined") {
    return;
  }
  var cfg = {};
  try {
    cfg = JSON.parse(el.getAttribute("data-config") || "{}");
  } catch (e) {
    cfg = {};
  }
  cfg.dom_id = "#swagger-ui";
  cfg.presets = [
    SwaggerUIBundle.presets.apis,
    SwaggerUIBundle.SwaggerUIStandalonePreset,
  ];
  SwaggerUIBundle(cfg);
})();
