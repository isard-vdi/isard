export interface FaroUser {
  id: string
  role: string
  sessionId?: string
}

let userImpl: ((user: FaroUser | null) => void) | null = null
let pendingUser: FaroUser | null | undefined = undefined

export function setFaroUser(user: FaroUser | null): void {
  if (userImpl) {
    userImpl(user)
  } else {
    // Faro not yet initialized — remember the latest call and replay it
    // as soon as registerFaroUserSetter runs.
    pendingUser = user
  }
}

export function registerFaroUserSetter(fn: (user: FaroUser | null) => void): void {
  userImpl = fn
  if (pendingUser !== undefined) {
    fn(pendingUser)
    pendingUser = undefined
  }
}

let viewImpl: ((name: string) => void) | null = null
let pendingView: string | undefined = undefined

export function setFaroView(name: string): void {
  if (viewImpl) {
    viewImpl(name)
  } else {
    pendingView = name
  }
}

export function registerFaroViewSetter(fn: (name: string) => void): void {
  viewImpl = fn
  if (pendingView !== undefined) {
    fn(pendingView)
    pendingView = undefined
  }
}

interface ErrorContext {
  info?: string
  component?: string
}

let errorImpl: ((err: unknown, context?: ErrorContext) => void) | null = null

/**
 * Report an error to Faro. Safe to call before `initFaro` runs (and after
 * FARO_ENABLED=false leaves Faro uninitialized): the call becomes a no-op.
 */
export function setFaroError(err: unknown, context?: ErrorContext): void {
  if (errorImpl) errorImpl(err, context)
}

export function registerFaroErrorHandler(fn: (err: unknown, context?: ErrorContext) => void): void {
  errorImpl = fn
}

export interface FaroApiEvent {
  client: 'auth' | 'api' | 'apiv4'
  method: string
  /**
   * OpenAPI path template with `{param}` placeholders (e.g.
   * `/item/category/{custom_url}`), taken directly from the generated
   * SDK's `options.url`. Used for dashboard grouping.
   */
  route_template: string
  status?: number
  outcome: 'completed' | 'failed'
  error_type?: 'http' | 'network'
  duration_ms: number
  request_id?: string
  response_size?: number
}

let apiEventImpl: ((info: FaroApiEvent) => void) | null = null

/**
 * Report a finished API request (success or failure) to Faro. Safe to
 * call before `initFaro` runs (and when Faro is disabled): the call is a
 * no-op in that case.
 */
export function setFaroApiEvent(info: FaroApiEvent): void {
  if (apiEventImpl) apiEventImpl(info)
}

export function registerFaroApiEventHandler(fn: (info: FaroApiEvent) => void): void {
  apiEventImpl = fn
}

let faroInitPromise: Promise<void> | null = null

/**
 * Lazy-load and initialize the Faro SDK from a server-supplied config block.
 * Called from the router guard once the authenticated user-config response
 * arrives. Idempotent: subsequent calls are no-ops.
 */
export function ensureFaroInitialized(faroConfig: {
  enabled: boolean
  url?: string | null
  http_sampling?: number
}): Promise<void> {
  if (!faroConfig.enabled || !faroConfig.url) return Promise.resolve()
  if (faroInitPromise) return faroInitPromise
  const url = faroConfig.url
  const httpSampling = faroConfig.http_sampling
  faroInitPromise = import('./faro').then(({ initFaro }) => {
    initFaro(url, { httpSampling })
  })
  return faroInitPromise
}

const ID_SEGMENT =
  /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|\d+|.{33,})$/i

/**
 * Collapse identifier-looking path segments into `{id}` so dashboards can
 * aggregate by page. Without it every desktop is its own page.
 */
export function pageIdFor(pathname: string): string {
  const collapsed = pathname
    .split('/')
    .map((segment) => (segment !== '' && ID_SEGMENT.test(segment) ? '{id}' : segment))
    .join('/')

  return collapsed === '' ? '/' : collapsed
}
