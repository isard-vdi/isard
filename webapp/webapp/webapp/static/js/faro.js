// Bootstraps the Grafana Faro Web SDK for the webapp (Flask/Jinja).
// The IIFE bundle exposes `window.GrafanaFaroWebSdk`. Loaded conditionally
// from base.html when FARO_ENABLED=true; this script is a no-op otherwise.
(function () {
  var sdk = window.GrafanaFaroWebSdk
  var cfg = window.__FARO_CONFIG__
  if (!sdk || !cfg || !cfg.url) return

  var faro = sdk.initializeFaro({
    url: cfg.url,
    app: {
      name: 'isardvdi-webapp',
      version: cfg.version || 'dev',
      environment: window.location.hostname
    },
    consoleInstrumentation: {
      disabledLevels: [
        sdk.LogLevel.LOG,
        sdk.LogLevel.INFO,
        sdk.LogLevel.DEBUG,
        sdk.LogLevel.TRACE
      ]
    },
    instrumentations: [].concat(
      sdk.getWebInstrumentations({
        captureConsole: false,
        enablePerformanceInstrumentation: true
      }),
      [new sdk.ConsoleInstrumentation()]
    )
  })

  faro.api.setView({ name: window.location.pathname || '/' })

  if (cfg.user && cfg.user.id) {
    var attrs = { role: cfg.user.role || 'anonymous' }
    if (cfg.user.category) attrs.category = cfg.user.category
    faro.api.setUser({ id: cfg.user.id, attributes: attrs })
  } else {
    faro.api.setUser({ attributes: { role: 'anonymous' } })
  }

  // Capture jQuery ajax failures (the webapp uses $.ajax/$.fn.dataTable,
  // which swallow errors before window.onerror sees them).
  if (window.jQuery) {
    window.jQuery(document).ajaxError(function (_event, jqxhr, settings, thrownError) {
      var url = settings && settings.url ? settings.url : ''
      var routeTemplate = url
      try {
        routeTemplate = new URL(url, window.location.origin).pathname
      } catch (e) {}
      faro.api.pushEvent('request_failed', {
        client: 'webapp',
        method: ((settings && settings.type) || 'GET').toUpperCase(),
        route_template: routeTemplate,
        duration_ms: '0',
        error_type: jqxhr && jqxhr.status ? 'http' : 'network',
        status: jqxhr && jqxhr.status ? String(jqxhr.status) : ''
      })
      if (!jqxhr || !jqxhr.status) {
        var err = thrownError instanceof Error
          ? thrownError
          : new Error(String(thrownError || 'ajax network error'))
        faro.api.pushError(err, { context: { source: 'jquery-ajaxError' } })
      }
    })
  }

  window.__faro = faro
})()
