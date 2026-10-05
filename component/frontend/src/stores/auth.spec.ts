// @vitest-environment-options {"url": "https://localhost/"}
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
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; secure`
  }
}

const HIDDEN_AT = 1_000_000

const leavePageWith = (cookies: { session?: string; authorization?: string }) => {
  vi.stubGlobal('performance', {
    timeOrigin: HIDDEN_AT,
    now: () => 0,
    getEntriesByType: () => []
  })
  if (cookies.session) {
    document.cookie = `isardvdi_session=${cookies.session}; path=/`
  }
  if (cookies.authorization) {
    document.cookie = `authorization=${cookies.authorization}; path=/; secure`
  }
  stashToken(useCookies())
  clearCookies()
}

beforeEach(() => {
  clearCookies()
  sessionStorage.clear()
  history.replaceState(null, '', '/reset-password')
  setActivePinia(createPinia())
})

afterEach(() => {
  clearCookies()
  sessionStorage.clear()
  vi.unstubAllGlobals()
})

const loadedBy = (type: string, startedAt = HIDDEN_AT - 3) =>
  vi.stubGlobal('performance', { timeOrigin: startedAt, getEntriesByType: () => [{ type }] })

describe('auth store: restoreStashedTokenOnBoot', () => {
  it.each(['reload', 'navigate'])(
    'gives a form login both its cookies back when the same page loads again by %s',
    (type) => {
      const token = resetToken(600)
      leavePageWith({ session: token, authorization: token })
      loadedBy(type)

      const store = useAuthStore()
      store.restoreStashedTokenOnBoot()

      expect(useCookies().get('isardvdi_session')).toBe(token)
      expect(useCookies().get('authorization')).toBe(token)
      expect(store.tokenType).toBe('password-reset-required')
      expect(takeStashedToken()).toBeUndefined()
    }
  )

  it('gives an external login back only the authorization cookie it had', () => {
    const token = resetToken(600)
    leavePageWith({ authorization: token })
    loadedBy('reload')

    const store = useAuthStore()
    store.restoreStashedTokenOnBoot()

    expect(useCookies().get('authorization')).toBe(token)
    expect(useCookies().get('isardvdi_session')).toBeUndefined()
    expect(store.token).toBe(token)
  })

  it('resumes the flow when the same page is opened again within the grace', () => {
    const token = resetToken(600)
    leavePageWith({ session: token, authorization: token })
    loadedBy('navigate', HIDDEN_AT + 3_000)

    useAuthStore().restoreStashedTokenOnBoot()

    expect(getBearer(useCookies())).toBe(token)
  })

  it('abandons the flow when the same page is opened again after the grace, e.g. back from another site', () => {
    const token = resetToken(600)
    leavePageWith({ session: token, authorization: token })
    loadedBy('navigate', HIDDEN_AT + 20_000)

    useAuthStore().restoreStashedTokenOnBoot()

    expect(getBearer(useCookies())).toBeUndefined()
    expect(takeStashedToken()).toBeUndefined()
  })

  it('abandons the flow on back/forward', () => {
    const token = resetToken(600)
    leavePageWith({ session: token, authorization: token })
    loadedBy('back_forward')

    useAuthStore().restoreStashedTokenOnBoot()

    expect(getBearer(useCookies())).toBeUndefined()
    expect(takeStashedToken()).toBeUndefined()
  })

  it('abandons the flow when another page loads, even across a later reload', () => {
    const token = resetToken(600)
    leavePageWith({ session: token, authorization: token })
    history.replaceState(null, '', '/login')
    loadedBy('navigate')

    useAuthStore().restoreStashedTokenOnBoot()
    expect(getBearer(useCookies())).toBeUndefined()

    setActivePinia(createPinia())
    loadedBy('reload')
    useAuthStore().restoreStashedTokenOnBoot()
    expect(getBearer(useCookies())).toBeUndefined()
  })

  it('drops an expired stashed token', () => {
    const token = resetToken(-5)
    leavePageWith({ session: token, authorization: token })
    loadedBy('reload')

    const store = useAuthStore()
    store.restoreStashedTokenOnBoot()

    expect(getBearer(useCookies())).toBeUndefined()
    expect(store.token).toBeNull()
    expect(takeStashedToken()).toBeUndefined()
  })

  it('never overwrites a session another tab has started meanwhile', () => {
    const token = resetToken(600)
    leavePageWith({ session: token, authorization: token })
    const other = buildJwt({ type: 'login', exp: Math.floor(Date.now() / 1000) + 600 })
    document.cookie = `isardvdi_session=${other}; path=/`
    loadedBy('reload')

    useAuthStore().restoreStashedTokenOnBoot()

    expect(getBearer(useCookies())).toBe(other)
    expect(useCookies().get('authorization')).toBeUndefined()
    expect(takeStashedToken()).toBeUndefined()
  })
})
