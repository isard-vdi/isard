import { beforeEach, describe, expect, it } from 'vitest'
import { instrumentClient } from './faro-api'
import { registerFaroApiEventHandler, type FaroApiEvent } from './faro-hook'

interface Interceptor<T> {
  use: (fn: T) => void
}

const buildClient = () => {
  const request: ((req: unknown, options: unknown) => unknown)[] = []
  const response: ((res: unknown, req: unknown, options: unknown) => unknown)[] = []
  const error: ((err: unknown, res: unknown, req: unknown, options: unknown) => unknown)[] = []

  return {
    client: {
      interceptors: {
        request: { use: (fn: never) => request.push(fn) } as Interceptor<never>,
        response: { use: (fn: never) => response.push(fn) } as Interceptor<never>,
        error: { use: (fn: never) => error.push(fn) } as Interceptor<never>
      }
    },
    request,
    response,
    error
  }
}

const headers = (entries: Record<string, string>) => ({
  get: (key: string) => entries[key] ?? null
})

describe('instrumentClient', () => {
  let events: FaroApiEvent[]

  beforeEach(() => {
    events = []
    registerFaroApiEventHandler((info) => events.push(info))
  })

  it('reports successful requests as completed', () => {
    const fake = buildClient()
    instrumentClient(fake.client as never, 'apiv4')

    const options = { method: 'get', url: '/item/desktop/{desktop_id}' }
    fake.request[0]({}, options)
    fake.response[0]({ status: 200, headers: headers({ 'content-length': '512' }) }, {}, options)

    expect(events).toHaveLength(1)
    expect(events[0].outcome).toBe('completed')
    expect(events[0].status).toBe(200)
    expect(events[0].method).toBe('GET')
    expect(events[0].route_template).toBe('/item/desktop/{desktop_id}')
    expect(events[0].response_size).toBe(512)
    expect(events[0].error_type).toBeUndefined()
  })

  it('keeps reporting failed requests exactly as before', () => {
    const fake = buildClient()
    instrumentClient(fake.client as never, 'apiv4')

    const options = { method: 'post', url: '/item/desktop' }
    fake.request[0]({}, options)
    fake.error[0](new Error('nope'), { status: 500, headers: headers({}) }, {}, options)

    expect(events).toHaveLength(1)
    expect(events[0].outcome).toBe('failed')
    expect(events[0].error_type).toBe('http')
    expect(events[0].status).toBe(500)
  })

  it('marks responseless failures as network errors', () => {
    const fake = buildClient()
    instrumentClient(fake.client as never, 'apiv4')

    const options = { method: 'get', url: '/item/desktop' }
    fake.request[0]({}, options)
    fake.error[0](new Error('offline'), undefined, {}, options)

    expect(events[0].error_type).toBe('network')
    expect(events[0].outcome).toBe('failed')
  })
})
