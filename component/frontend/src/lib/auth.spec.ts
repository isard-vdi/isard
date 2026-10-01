// @vitest-environment-options {"url": "https://localhost/"}
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  TokenType,
  isRegisterClaims,
  isReRegisterClaims,
  discardStashedToken,
  isReloadOf,
  parseToken,
  restoreStashedCookies,
  stashToken,
  takeStashedToken,
  useCookies
} from './auth'

const buildJwt = (payload: object): string => {
  const encode = (o: object) =>
    btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')

  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`
}

describe('parseToken', () => {
  it('parses a re-register token as ReRegisterClaims', () => {
    const claims = parseToken(
      buildJwt({ type: 're-register', provider: 'saml', category_id: 'default' })
    )

    expect(claims.type).toBe(TokenType.ReRegister)
    expect(isReRegisterClaims(claims)).toBe(true)
    expect(isRegisterClaims(claims)).toBe(false)
  })

  it('keeps register tokens as RegisterClaims', () => {
    const claims = parseToken(
      buildJwt({ type: 'register', provider: 'saml', category_id: 'default' })
    )

    expect(isRegisterClaims(claims)).toBe(true)
    expect(isReRegisterClaims(claims)).toBe(false)
  })
})

const setAuthCookie = (name: 'isardvdi_session' | 'authorization', value: string) => {
  document.cookie = `${name}=${value}; path=/${name === 'authorization' ? '; secure' : ''}`
}

const clearAuthCookies = () => {
  for (const name of ['isardvdi_session', 'authorization']) {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; secure`
  }
}

describe('token stash', () => {
  beforeEach(() => {
    history.replaceState(null, '', '/reset-password')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    sessionStorage.clear()
    clearAuthCookies()
  })

  it('keeps both auth cookies and the page they were taken on, exactly once', () => {
    setAuthCookie('isardvdi_session', 'the.session.token')
    setAuthCookie('authorization', 'the.authorization.token')

    stashToken(useCookies())

    expect(takeStashedToken()).toEqual({
      url: '/reset-password',
      hiddenAt: expect.any(Number),
      session: 'the.session.token',
      authorization: 'the.authorization.token'
    })
    expect(takeStashedToken()).toBeUndefined()
  })

  it('keeps only the cookie an external login left behind', () => {
    setAuthCookie('authorization', 'the.authorization.token')

    stashToken(useCookies())

    expect(takeStashedToken()).toEqual({
      url: '/reset-password',
      hiddenAt: expect.any(Number),
      authorization: 'the.authorization.token'
    })
  })

  it('stashes nothing when there is no auth cookie', () => {
    stashToken(useCookies())

    expect(sessionStorage.length).toBe(0)
  })

  it.each([
    'a.plain.legacy.token',
    JSON.stringify({ url: '/reset-password', session: 'the.session.token' })
  ])('ignores a stash it cannot use: %s', (raw) => {
    sessionStorage.setItem('isardvdi_intermediate_token', raw)

    expect(takeStashedToken()).toBeUndefined()
  })

  it('discards the stash without handing it back', () => {
    setAuthCookie('isardvdi_session', 'the.session.token')
    stashToken(useCookies())

    discardStashedToken()

    expect(takeStashedToken()).toBeUndefined()
  })

  it('treats unavailable storage as an empty stash', () => {
    setAuthCookie('isardvdi_session', 'the.session.token')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(() => stashToken(useCookies())).not.toThrow()
    expect(takeStashedToken()).toBeUndefined()
  })
})

describe('restoreStashedCookies', () => {
  const fakeCookies = () => ({ set: vi.fn() }) as unknown as ReturnType<typeof useCookies>
  const tokenExpiringIn = (seconds: number) => {
    const exp = Math.floor(Date.now() / 1000) + seconds
    return { exp, token: buildJwt({ type: 'password-reset-required', exp }) }
  }

  it('re-creates each cookie with the attributes it was originally set with', () => {
    const { exp, token } = tokenExpiringIn(600)
    const cookies = fakeCookies()

    expect(
      restoreStashedCookies(cookies, {
        url: '/reset-password',
        hiddenAt: 0,
        session: token,
        authorization: token
      })
    ).toBe(true)

    expect(cookies.set).toHaveBeenCalledWith('authorization', token, {
      path: '/',
      sameSite: 'strict',
      secure: true,
      expires: new Date(exp * 1000)
    })
    expect(cookies.set).toHaveBeenCalledWith('isardvdi_session', token, {
      path: '/',
      sameSite: 'strict'
    })
  })

  it('does not create a cookie that was not there before', () => {
    const { token } = tokenExpiringIn(600)
    const cookies = fakeCookies()

    restoreStashedCookies(cookies, { url: '/register', hiddenAt: 0, authorization: token })

    expect(cookies.set).toHaveBeenCalledOnce()
    expect(cookies.set).toHaveBeenCalledWith('authorization', token, expect.any(Object))
  })

  it('skips expired tokens', () => {
    const { token } = tokenExpiringIn(-5)
    const cookies = fakeCookies()

    expect(
      restoreStashedCookies(cookies, {
        url: '/reset-password',
        hiddenAt: 0,
        session: token,
        authorization: token
      })
    ).toBe(false)
    expect(cookies.set).not.toHaveBeenCalled()
  })
})

describe('isReloadOf', () => {
  beforeEach(() => {
    history.replaceState(null, '', '/reset-password?step=1')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const stashed = { url: '/reset-password?step=1', hiddenAt: 1_000_000 }

  const loadedBy = (type?: string, startedAt = stashed.hiddenAt - 3) =>
    vi.stubGlobal('performance', {
      timeOrigin: startedAt,
      getEntriesByType: () => (type ? [{ type }] : [])
    })

  it.each(['reload', 'navigate'])('is true when the same page loads again by %s', (type) => {
    loadedBy(type)
    expect(isReloadOf(stashed)).toBe(true)
  })

  it.each(['reload', 'navigate'])(
    'is true for a %s that started within the grace after the page was left',
    (type) => {
      loadedBy(type, stashed.hiddenAt + 9_000)
      expect(isReloadOf(stashed)).toBe(true)
    }
  )

  it.each([11_000, 20_000])(
    'is false for a load that started %i ms after the page was left, e.g. back from another site',
    (delay) => {
      loadedBy('navigate', stashed.hiddenAt + delay)
      expect(isReloadOf(stashed)).toBe(false)
    }
  )

  it('is false on back/forward, even to the same page', () => {
    loadedBy('back_forward')
    expect(isReloadOf(stashed)).toBe(false)
  })

  it.each(['reload', 'navigate'])('is false when another page loads by %s', (type) => {
    loadedBy(type)
    expect(isReloadOf({ ...stashed, url: '/login' })).toBe(false)
  })

  it('is false when the load type is unknown', () => {
    loadedBy(undefined)
    expect(isReloadOf(stashed)).toBe(false)
  })
})
