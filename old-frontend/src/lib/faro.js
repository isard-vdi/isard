import {
  ConsoleInstrumentation,
  getWebInstrumentations,
  initializeFaro,
  LogLevel
} from '@grafana/faro-web-sdk'

let faro = null
let httpSampling = 1
let currentView = null
// The router emits its first `afterEach` long before the config response
// finishes initialising Faro, so hold that view here and replay it once the
// SDK exists. Without it a single-page session never starts the dwell timer
// and emits no `view_time` at all. Mirrors `pendingView` in the Vue 3
// frontend's faro-hook.ts.
let pendingView = null
// Same race for the identity: `setSession` lands the token before
// `fetchConfig` initialises Faro, so park the user and replay it on init.
// `undefined` means "nothing parked"; `null` is a parked logout.
let pendingUser

const ID_SEGMENT =
  /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|\d+|.{33,})$/i

/**
 * Collapse identifier-looking path segments into `{id}` so dashboards can
 * aggregate by page. Without it every desktop is its own page.
 */
export function pageIdFor (pathname) {
  const collapsed = pathname
    .split('/')
    .map((segment) => (segment !== '' && ID_SEGMENT.test(segment) ? '{id}' : segment))
    .join('/')

  return collapsed === '' ? '/' : collapsed
}

function flushViewTime () {
  if (!faro || !currentView) return
  const { name, started } = currentView
  currentView = null
  faro.api.pushEvent('view_time', {
    view_name: name,
    page_id: pageIdFor(name),
    duration_ms: String(Math.round(performance.now() - started))
  })
}

export function initFaro (url, options) {
  if (faro) return
  httpSampling = options?.httpSampling ?? 1
  faro = initializeFaro({
    url,
    app: {
      name: 'isardvdi-old-frontend',
      version: typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev',
      environment: window.location.hostname
    },
    consoleInstrumentation: {
      disabledLevels: [LogLevel.LOG, LogLevel.INFO, LogLevel.DEBUG, LogLevel.TRACE]
    },
    pageTracking: {
      generatePageId: (location) => pageIdFor(location.pathname)
    },
    instrumentations: [
      ...getWebInstrumentations({
        captureConsole: false,
        enablePerformanceInstrumentation: true
      }),
      new ConsoleInstrumentation()
    ]
  })

  faro.api.setView({ name: window.location.pathname || '/' })
  faro.api.setUser({ attributes: { role: 'anonymous' } })

  window.addEventListener('pagehide', flushViewTime)

  // Replay the identity the auth store already resolved. Must come after the
  // anonymous seed above, or that seed would overwrite it.
  if (pendingUser !== undefined) {
    const user = pendingUser
    pendingUser = undefined
    setFaroUser(user)
  }

  // Replay the view the router already announced. This is what actually
  // starts the dwell timer; the seed above only exists so errors thrown
  // before this point carry some `view_name`.
  if (pendingView !== null) {
    const name = pendingView
    pendingView = null
    setFaroView(name)
  }
}

export function setFaroUser (user) {
  if (!faro) {
    pendingUser = user
    return
  }
  if (!user) {
    faro.api.setUser({ attributes: { role: 'anonymous' } })
    return
  }
  const attributes = { role: user.role }
  if (user.sessionId) attributes.sessionId = user.sessionId
  faro.api.setUser({ id: user.id, attributes })
}

export function setFaroView (name) {
  if (!faro) {
    pendingView = name
    return
  }
  flushViewTime()
  faro.api.setView({ name })
  currentView = { name, started: performance.now() }
}

export function setFaroError (err, context) {
  if (!faro) return
  const error = err instanceof Error ? err : new Error(String(err))
  faro.api.pushError(error, {
    context: {
      source: context?.source ?? 'vue-errorHandler',
      ...(context?.info ? { vue_info: context.info } : {}),
      ...(context?.component ? { vue_component: context.component } : {})
    }
  })
}

export function setFaroApiEvent (info) {
  if (!faro) return
  if (info.outcome === 'completed' && Math.random() >= httpSampling) return
  const ctx = {
    client: info.client,
    method: info.method,
    route_template: info.route_template,
    duration_ms: String(info.duration_ms)
  }
  // A network failure never got a response, so it has no HTTP status. Report
  // it as 0 — the value the dashboard's `$status` picker offers for exactly
  // this case — instead of dropping the attribute.
  const status = info.status ?? (info.error_type === 'network' ? 0 : undefined)
  if (info.error_type) ctx.error_type = info.error_type
  if (status !== undefined) ctx.status = String(status)
  if (info.request_id) ctx.request_id = info.request_id
  if (info.response_size !== undefined) ctx.response_size = String(info.response_size)
  faro.api.pushEvent(info.outcome === 'failed' ? 'request_failed' : 'request_completed', ctx)
}
