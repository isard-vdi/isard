import {
  ConsoleInstrumentation,
  getWebInstrumentations,
  initializeFaro,
  LogLevel,
  type Faro
} from '@grafana/faro-web-sdk'
import {
  pageIdFor,
  registerFaroApiEventHandler,
  registerFaroErrorHandler,
  registerFaroUserSetter,
  registerFaroViewSetter,
  type FaroUser
} from './faro-hook'

let faro: Faro | null = null

export type { FaroUser }

/**
 * Initialize the Faro SDK. Called once from main.ts when runtime config
 * reports faro.enabled=true. Idempotent on repeated calls.
 */
export function initFaro(url: string, options?: { httpSampling?: number }): void {
  if (faro) return
  const httpSampling = options?.httpSampling ?? 1
  faro = initializeFaro({
    url,
    app: {
      name: 'isardvdi-frontend',
      version: __APP_VERSION__,
      environment: window.location.hostname
    },
    // Only capture warn and error; suppress log/info/debug/trace noise.
    // In v2.4.0, disabledLevels is a top-level config key read by ConsoleInstrumentation
    // at initialise-time — it is NOT passed to the constructor.
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

  // Seed anonymous *before* registering the setter: registering replays the
  // user parked by the auth store during bootstrap, and seeding afterwards
  // would overwrite that authenticated identity with `anonymous`.
  faro.api.setUser({ attributes: { role: 'anonymous' } })

  registerFaroUserSetter((user) => {
    if (!faro) return
    if (!user) {
      faro.api.setUser({ attributes: { role: 'anonymous' } })
      return
    }
    const attributes: Record<string, string> = { role: user.role }
    if (user.sessionId) attributes.sessionId = user.sessionId
    faro.api.setUser({ id: user.id, attributes })
  })

  let currentView: { name: string; started: number } | null = null

  const flushViewTime = (): void => {
    if (!faro || !currentView) return
    const { name, started } = currentView
    currentView = null
    faro.api.pushEvent('view_time', {
      view_name: name,
      page_id: pageIdFor(name),
      duration_ms: String(Math.round(performance.now() - started))
    })
  }

  registerFaroViewSetter((name) => {
    if (!faro) return
    flushViewTime()
    faro.api.setView({ name })
    currentView = { name, started: performance.now() }
  })

  // Seed a view name immediately from the current location so events emitted
  // before the router finishes its first navigation (errors thrown during
  // component setup/mount) still carry a `view_name`.
  const initialView = window.location.pathname || '/'
  faro.api.setView({ name: initialView })

  window.addEventListener('pagehide', flushViewTime)

  registerFaroErrorHandler((err, context) => {
    if (!faro) return
    const error = err instanceof Error ? err : new Error(String(err))
    faro.api.pushError(error, {
      context: {
        source: 'vue-errorHandler',
        ...(context?.info ? { vue_info: context.info } : {}),
        ...(context?.component ? { vue_component: context.component } : {})
      }
    })
  })

  registerFaroApiEventHandler((info) => {
    if (!faro) return
    if (info.outcome === 'completed' && Math.random() >= httpSampling) return
    // A network failure never got a response, so it has no HTTP status. Report
    // it as 0 — the value the dashboard's `$status` picker offers for exactly
    // this case — instead of dropping the attribute.
    const status = info.status ?? (info.error_type === 'network' ? 0 : undefined)
    faro.api.pushEvent(info.outcome === 'failed' ? 'request_failed' : 'request_completed', {
      client: info.client,
      method: info.method,
      route_template: info.route_template,
      duration_ms: String(info.duration_ms),
      ...(info.error_type && { error_type: info.error_type }),
      ...(status !== undefined && { status: String(status) }),
      ...(info.request_id && { request_id: info.request_id }),
      ...(info.response_size !== undefined && {
        response_size: String(info.response_size)
      })
    })
  })
}
