import {
  ConsoleInstrumentation,
  getWebInstrumentations,
  initializeFaro,
  LogLevel,
  type Faro
} from '@grafana/faro-web-sdk'
import {
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
export function initFaro(url: string): void {
  if (faro) return
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
    instrumentations: [
      ...getWebInstrumentations({
        captureConsole: false,
        enablePerformanceInstrumentation: true
      }),
      new ConsoleInstrumentation()
    ]
  })

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

  faro.api.setUser({ attributes: { role: 'anonymous' } })

  registerFaroViewSetter((name) => {
    if (!faro) return
    faro.api.setView({ name })
  })

  // Seed a view name immediately from the current location so events emitted
  // before the router finishes its first navigation (errors thrown during
  // component setup/mount) still carry a `view_name`.
  faro.api.setView({ name: window.location.pathname || '/' })

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
    faro.api.pushEvent('request_failed', {
      client: info.client,
      method: info.method,
      route_template: info.route_template,
      error_type: info.error_type,
      duration_ms: String(info.duration_ms),
      ...(info.status !== undefined && { status: String(info.status) }),
      ...(info.request_id && { request_id: info.request_id }),
      ...(info.response_size !== undefined && {
        response_size: String(info.response_size)
      })
    })
  })
}
