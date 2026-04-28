import {
  ConsoleInstrumentation,
  getWebInstrumentations,
  initializeFaro,
  LogLevel
} from '@grafana/faro-web-sdk'

let faro = null

export function initFaro (url) {
  if (faro) return
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
}

export function setFaroUser (user) {
  if (!faro) return
  if (!user) {
    faro.api.setUser({ attributes: { role: 'anonymous' } })
    return
  }
  const attributes = { role: user.role }
  if (user.sessionId) attributes.sessionId = user.sessionId
  faro.api.setUser({ id: user.id, attributes })
}

export function setFaroView (name) {
  if (!faro) return
  faro.api.setView({ name })
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
  const ctx = {
    client: info.client,
    method: info.method,
    route_template: info.route_template,
    error_type: info.error_type,
    duration_ms: String(info.duration_ms)
  }
  if (info.status !== undefined) ctx.status = String(info.status)
  if (info.request_id) ctx.request_id = info.request_id
  if (info.response_size !== undefined) ctx.response_size = String(info.response_size)
  faro.api.pushEvent('request_failed', ctx)
}
