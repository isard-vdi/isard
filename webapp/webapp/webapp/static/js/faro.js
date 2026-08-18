// Bootstraps the Grafana Faro Web SDK for the webapp (Flask/Jinja).
// The IIFE bundle exposes `window.GrafanaFaroWebSdk`. Loaded conditionally
// from base.html when FARO_ENABLED=true; this script is a no-op otherwise.
(function () {
  var sdk = window.GrafanaFaroWebSdk
  var cfg = window.__FARO_CONFIG__
  if (!sdk || !cfg || !cfg.url) return

  var httpSampling = typeof cfg.httpSampling === 'number' ? cfg.httpSampling : 1

  var ID_SEGMENT =
    /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|\d+|.{33,})$/i

  // Collapse identifier-looking path segments into `{id}` so dashboards can
  // aggregate by page. Without it every desktop is its own page.
  function pageIdFor (pathname) {
    var collapsed = pathname
      .split('/')
      .map(function (segment) {
        return segment !== '' && ID_SEGMENT.test(segment) ? '{id}' : segment
      })
      .join('/')

    return collapsed === '' ? '/' : collapsed
  }

  // Strip token-bearing path segments and querystrings so Faro's
  // route_template stays a low-cardinality, OpenAPI-shaped value.
  function routeTemplateFor (urlString) {
    try {
      return pageIdFor(new URL(urlString, window.location.origin).pathname)
    } catch (e) {
      return pageIdFor(urlString.split('?')[0])
    }
  }

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
    pageTracking: {
      generatePageId: function (location) {
        return pageIdFor(location.pathname)
      }
    },
    instrumentations: [].concat(
      sdk.getWebInstrumentations({
        captureConsole: false,
        enablePerformanceInstrumentation: true
      }),
      [new sdk.ConsoleInstrumentation()]
    )
  })

  var currentView = null

  function flushViewTime () {
    if (!currentView) return
    var view = currentView
    currentView = null
    faro.api.pushEvent('view_time', {
      view_name: view.name,
      page_id: pageIdFor(view.name),
      duration_ms: String(Math.round(performance.now() - view.started))
    })
  }

  // The webapp has no client-side router, so this page load is its only view:
  // start the dwell timer here, because no later setView will ever flush it.
  var initialView = window.location.pathname || '/'
  faro.api.setView({ name: initialView })
  currentView = { name: initialView, started: performance.now() }

  window.addEventListener('pagehide', flushViewTime)

  if (cfg.user && cfg.user.id) {
    var attrs = { role: cfg.user.role || 'anonymous' }
    if (cfg.user.category) attrs.category = cfg.user.category
    faro.api.setUser({ id: cfg.user.id, attributes: attrs })
  } else {
    faro.api.setUser({ attributes: { role: 'anonymous' } })
  }

  // Capture jQuery ajax completions and failures (the webapp uses
  // $.ajax/$.fn.dataTable, which swallow errors before window.onerror
  // sees them).
  if (window.jQuery) {
    window.jQuery(document).ajaxSend(function (_event, jqxhr) {
      jqxhr.faroStarted = performance.now()
    })

    // ajaxComplete fires for every request, successful or not.
    window.jQuery(document).ajaxComplete(function (_event, jqxhr, settings) {
      var status = (jqxhr && jqxhr.status) || 0
      var failed = status < 200 || status >= 300
      if (!failed && Math.random() >= httpSampling) return

      var payload = {
        client: 'webapp',
        method: ((settings && settings.type) || 'GET').toUpperCase(),
        route_template: routeTemplateFor((settings && settings.url) || ''),
        // A network failure never got a response, so it has no HTTP status.
        // Report it as 0 — the value the dashboard's `$status` picker offers
        // for exactly this case.
        status: String(status)
      }
      if (failed) payload.error_type = status ? 'http' : 'network'
      // Omit the duration rather than fabricate one for a request that was
      // already in flight when this script attached its listeners.
      if (jqxhr.faroStarted) {
        payload.duration_ms = String(Math.round(performance.now() - jqxhr.faroStarted))
      }
      faro.api.pushEvent(failed ? 'request_failed' : 'request_completed', payload)
    })

    window.jQuery(document).ajaxError(function (_event, jqxhr, _settings, thrownError) {
      if (jqxhr && jqxhr.status) return
      var err = thrownError instanceof Error
        ? thrownError
        : new Error(String(thrownError || 'ajax network error'))
      faro.api.pushError(err, { context: { source: 'jquery-ajaxError' } })
    })
  }

  window.__faro = faro
})()
