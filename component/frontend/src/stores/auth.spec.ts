import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/gen/oas/authentication', () => ({ renew: vi.fn() }))

import { getBearer, stashToken, takeStashedToken, useCookies } from '@/lib/auth'
import { useAuthStore } from './auth'

const buildJwt = (payload: object): string => {
  const encode = (o: object) =>
    btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`
}

const resetToken = (expiresInSeconds: number) =>
  buildJwt({
    type: 'password-reset-required',
    user_id: 'u1',
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds
  })

const clearCookies = () => {
  for (const name of ['isardvdi_session', 'authorization']) {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
  }
}

describe('auth store: restoreStashedToken', () => {
  beforeEach(() => {
    clearCookies()
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    clearCookies()
    sessionStorage.clear()
  })

  it('puts a still-valid stashed token back after a reload', () => {
    const token = resetToken(600)
    stashToken(token)

    const store = useAuthStore()
    store.restoreStashedToken()

    expect(getBearer(useCookies())).toBe(token)
    expect(store.token).toBe(token)
    expect(store.tokenType).toBe('password-reset-required')
    expect(takeStashedToken()).toBeUndefined()
  })

  it('drops an expired stashed token', () => {
    stashToken(resetToken(-5))

    const store = useAuthStore()
    store.restoreStashedToken()

    expect(getBearer(useCookies())).toBeUndefined()
    expect(store.token).toBeNull()
    expect(takeStashedToken()).toBeUndefined()
  })

  it('never overwrites a session another tab has started meanwhile', () => {
    const other = buildJwt({ type: 'login', exp: Math.floor(Date.now() / 1000) + 600 })
    document.cookie = `isardvdi_session=${other}; path=/`
    stashToken(resetToken(600))

    const store = useAuthStore()
    store.restoreStashedToken()

    expect(getBearer(useCookies())).toBe(other)
    expect(takeStashedToken()).toBeUndefined()
  })
})
