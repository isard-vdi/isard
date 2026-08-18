import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const pushEvent = vi.fn()
const setView = vi.fn()
const setUser = vi.fn()

vi.mock('@grafana/faro-web-sdk', () => ({
  initializeFaro: () => ({ api: { pushEvent, setView, setUser, pushError: vi.fn() } }),
  getWebInstrumentations: () => [],
  // eslint-disable-next-line @typescript-eslint/no-extraneous-class -- deliberately empty test double for the constructible `ConsoleInstrumentation` export
  ConsoleInstrumentation: class {},
  LogLevel: { LOG: 'log', INFO: 'info', DEBUG: 'debug', TRACE: 'trace' }
}))

describe('view_time', () => {
  beforeEach(() => {
    vi.resetModules()
    pushEvent.mockClear()
    setView.mockClear()
  })

  // Each test's `initFaro` attaches its own `pagehide` listener to the
  // shared, file-scoped jsdom `window` (vi.resetModules() only resets the
  // module cache, not `window`). Draining here stops a still-attached
  // listener from a previous test firing on a later test's `pagehide`
  // dispatch and double-counting `view_time` events. Also reset the
  // location back to `/` so a test that navigates via `history.pushState`
  // doesn't leak that navigation into the next test.
  afterEach(() => {
    window.dispatchEvent(new Event('pagehide'))
    history.pushState({}, '', '/')
  })

  it('reports the time spent on the previous view when the view changes', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroView } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroView('/desktops')
    setFaroView('/deployments/12345')

    const viewTimes = pushEvent.mock.calls.filter(([name]) => name === 'view_time')
    expect(viewTimes).toHaveLength(1)
    expect(viewTimes[0][1].view_name).toBe('/desktops')
    expect(typeof viewTimes[0][1].duration_ms).toBe('string')
  })

  it('reports the current view on pagehide', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroView } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroView('/desktops')
    window.dispatchEvent(new Event('pagehide'))

    const viewTimes = pushEvent.mock.calls.filter(([name]) => name === 'view_time')
    expect(viewTimes).toHaveLength(1)
    expect(viewTimes[0][1].view_name).toBe('/desktops')
  })

  it('does not report twice for the same view', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroView } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroView('/desktops')
    window.dispatchEvent(new Event('pagehide'))
    window.dispatchEvent(new Event('pagehide'))

    expect(pushEvent.mock.calls.filter(([name]) => name === 'view_time')).toHaveLength(1)
  })

  it('reports the page_id of the flushed view, not the destination the router already navigated to', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroView } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroView('/desktops')

    // The real router's afterEach hook calls setFaroView only after
    // history.pushState has already landed on the destination, so
    // window.location is already the *new* route by the time the
    // *previous* view's view_time gets flushed.
    history.pushState({}, '', '/deployments/12345')
    setFaroView('/deployments/12345')

    const viewTimes = pushEvent.mock.calls.filter(([name]) => name === 'view_time')
    expect(viewTimes).toHaveLength(1)
    expect(viewTimes[0][1].view_name).toBe('/desktops')
    expect(viewTimes[0][1].page_id).toBe('/desktops')
  })
})

describe('http_sampling guard', () => {
  beforeEach(() => {
    vi.resetModules()
    pushEvent.mockClear()
    setView.mockClear()
  })

  it('reports a completed request when httpSampling is 1', async () => {
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect', { httpSampling: 1 })
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'completed',
      duration_ms: 12
    })

    const completed = pushEvent.mock.calls.filter(([name]) => name === 'request_completed')
    expect(completed).toHaveLength(1)
    randomSpy.mockRestore()
  })

  it('does not report a completed request when httpSampling is 0', async () => {
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect', { httpSampling: 0 })
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'completed',
      duration_ms: 12
    })

    const completed = pushEvent.mock.calls.filter(([name]) => name === 'request_completed')
    expect(completed).toHaveLength(0)
    randomSpy.mockRestore()
  })

  it('always reports a failed request even when httpSampling is 0', async () => {
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0)
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect', { httpSampling: 0 })
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'failed',
      duration_ms: 12
    })

    const failed = pushEvent.mock.calls.filter(([name]) => name === 'request_failed')
    expect(failed).toHaveLength(1)
    randomSpy.mockRestore()
  })
})

describe('user identity', () => {
  beforeEach(() => {
    vi.resetModules()
    pushEvent.mockClear()
    setView.mockClear()
    setUser.mockClear()
  })

  // The auth store's watcher runs with `immediate: true` during app
  // bootstrap, long before the router guard fetches the user config and
  // initialises Faro. That call parks the user in `pendingUser`, and
  // `registerFaroUserSetter` replays it — so the anonymous seed must be
  // written *before* the setter is registered, or it overwrites the
  // authenticated identity and every event ships as `role=anonymous`.
  it('keeps a user set before initFaro instead of resetting it to anonymous', async () => {
    const { setFaroUser } = await import('./faro-hook')
    const { initFaro } = await import('./faro')

    setFaroUser({ id: 'local-default-admin-admin', role: 'admin', sessionId: 'abc123' })
    initFaro('/faro/collect')

    expect(setUser).toHaveBeenLastCalledWith({
      id: 'local-default-admin-admin',
      attributes: { role: 'admin', sessionId: 'abc123' }
    })
  })

  it('seeds anonymous when no user was set before initFaro', async () => {
    const { initFaro } = await import('./faro')

    initFaro('/faro/collect')

    expect(setUser).toHaveBeenLastCalledWith({ attributes: { role: 'anonymous' } })
  })

  it('applies a user set after initFaro', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroUser } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroUser({ id: 'local-default-user-user', role: 'user' })

    expect(setUser).toHaveBeenLastCalledWith({
      id: 'local-default-user-user',
      attributes: { role: 'user' }
    })
  })

  it('falls back to anonymous on logout', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroUser } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroUser({ id: 'local-default-admin-admin', role: 'admin' })
    setFaroUser(null)

    expect(setUser).toHaveBeenLastCalledWith({ attributes: { role: 'anonymous' } })
  })

  it('honours a logout parked before initFaro', async () => {
    const { setFaroUser } = await import('./faro-hook')
    const { initFaro } = await import('./faro')

    setFaroUser(null)
    initFaro('/faro/collect')

    expect(setUser).toHaveBeenLastCalledWith({ attributes: { role: 'anonymous' } })
  })
})

describe('request_failed status', () => {
  beforeEach(() => {
    vi.resetModules()
    pushEvent.mockClear()
    setView.mockClear()
  })

  // A network failure has no HTTP status, but the dashboard's `$status`
  // picker offers a `0` value for exactly this case. Omitting the attribute
  // makes network failures invisible in the status dimension.
  it("reports status '0' for a network error", async () => {
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'failed',
      error_type: 'network',
      duration_ms: 12
    })

    const failed = pushEvent.mock.calls.filter(([name]) => name === 'request_failed')
    expect(failed).toHaveLength(1)
    expect(failed[0][1].status).toBe('0')
  })

  it('keeps the real status for an http error', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'failed',
      error_type: 'http',
      status: 500,
      duration_ms: 12
    })

    const failed = pushEvent.mock.calls.filter(([name]) => name === 'request_failed')
    expect(failed).toHaveLength(1)
    expect(failed[0][1].status).toBe('500')
  })

  it('does not invent a status for a request that reports none', async () => {
    const { initFaro } = await import('./faro')
    const { setFaroApiEvent } = await import('./faro-hook')

    initFaro('/faro/collect')
    setFaroApiEvent({
      client: 'apiv4',
      method: 'GET',
      route_template: '/item/desktop',
      outcome: 'completed',
      duration_ms: 12
    })

    const completed = pushEvent.mock.calls.filter(([name]) => name === 'request_completed')
    expect(completed).toHaveLength(1)
    expect(completed[0][1].status).toBeUndefined()
  })
})
