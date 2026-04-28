// The three gen clients (auth/api/apiv4) are generated from the same
// @hey-api/openapi-ts template and share identical `Client` shapes. Any one
// of them exposes the 4-param `Middleware<Request, Response, unknown,
// ResolvedRequestOptions>` with the `error` interceptor channel that the
// public `@hey-api/client-fetch` types omit, so we pick apiv4 arbitrarily.
import type { Client } from '@/gen/oas/apiv4/client'
import { setFaroApiEvent, setFaroError, type FaroApiEvent } from './faro-hook'

/**
 * Instrument an @hey-api/openapi-ts client so every failed request (network
 * error or non-2xx) is reported to Faro. Safe no-op when Faro is disabled.
 *
 * Uses the generated SDK's `options.url` — the OpenAPI path template with
 * `{param}` placeholders — as `route_template`, so no runtime path
 * normalisation is needed.
 */
export function instrumentClient(client: Client, name: FaroApiEvent['client']): void {
  const starts = new WeakMap<object, number>()

  client.interceptors.request.use((request, options) => {
    starts.set(options, performance.now())
    return request
  })

  client.interceptors.error.use((err, response, _request, options) => {
    const started = starts.get(options) ?? performance.now()
    setFaroApiEvent({
      client: name,
      method: (options.method ?? 'GET').toUpperCase(),
      route_template: options.url,
      duration_ms: Math.round(performance.now() - started),
      error_type: response ? 'http' : 'network',
      status: response?.status,
      request_id: response?.headers.get('x-request-id') ?? undefined,
      response_size: Number(response?.headers.get('content-length')) || undefined
    })
    if (!response) {
      setFaroError(err, { info: 'api_network_error', component: name })
    }
    return err
  })
}
