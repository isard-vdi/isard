import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TokenType } from '@/lib/auth'

const mocks = vi.hoisted(() => ({
  leaveGuard: undefined as (() => unknown) | undefined,
  listeners: {} as Record<string, (event: { persisted?: boolean }) => void>,
  cookieToken: undefined as { type: string } | undefined,
  cookies: {},
  store: {
    tokenType: undefined as string | undefined,
    logout: vi.fn(),
    $reset: vi.fn()
  },
  stashToken: vi.fn(),
  discardStashedToken: vi.fn(),
  removeToken: vi.fn(),
  routerGo: vi.fn()
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (guard: () => unknown) => {
    mocks.leaveGuard = guard
  },
  useRouter: () => ({ go: mocks.routerGo })
}))

vi.mock('@vueuse/core', () => ({
  useEventListener: (_target: unknown, event: string, handler: () => void) => {
    mocks.listeners[event] = handler
  }
}))

vi.mock('@/lib/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/auth')>()),
  useCookies: () => mocks.cookies,
  getToken: () => mocks.cookieToken,
  getBearer: () => (mocks.cookieToken ? 'the.cookie.bearer' : undefined),
  stashToken: mocks.stashToken,
  discardStashedToken: mocks.discardStashedToken,
  removeToken: mocks.removeToken
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => mocks.store
}))

import { useClearTokenOnLeave } from './useClearTokenOnLeave'

const VIEW_TYPES = [TokenType.PasswordResetRequired, TokenType.PasswordReset]

const leaveWith = (tokenType: string | undefined) => {
  mocks.store.tokenType = tokenType
  useClearTokenOnLeave(VIEW_TYPES)
  mocks.leaveGuard?.()
}

const hidePageWith = (cookieType: string | undefined, storeType = cookieType) => {
  mocks.cookieToken = cookieType ? { type: cookieType } : undefined
  mocks.store.tokenType = storeType
  useClearTokenOnLeave(VIEW_TYPES)
  mocks.listeners.pagehide({ persisted: false })
}

describe('useClearTokenOnLeave', () => {
  beforeEach(() => {
    mocks.leaveGuard = undefined
    mocks.listeners = {}
    mocks.cookieToken = undefined
    vi.clearAllMocks()
  })

  describe('in-app navigation', () => {
    it.each(VIEW_TYPES)('logs out when leaving with the view token %s still stored', (type) => {
      leaveWith(type)
      expect(mocks.store.logout).toHaveBeenCalledOnce()
    })

    it('keeps a login token the view has just stored before navigating', () => {
      leaveWith(TokenType.Login)
      expect(mocks.store.logout).not.toHaveBeenCalled()
    })

    it("keeps another view's intermediate token", () => {
      leaveWith(TokenType.EmailVerificationRequired)
      expect(mocks.store.logout).not.toHaveBeenCalled()
    })

    it('does nothing when there is no token', () => {
      leaveWith(undefined)
      expect(mocks.store.logout).not.toHaveBeenCalled()
    })
  })

  describe('closing, reloading or leaving the page', () => {
    it('moves the view token out of the cookies into the tab-scoped stash', () => {
      hidePageWith(TokenType.PasswordResetRequired)

      expect(mocks.stashToken).toHaveBeenCalledWith(mocks.cookies)
      expect(mocks.removeToken).toHaveBeenCalledOnce()
      expect(mocks.store.$reset).toHaveBeenCalledOnce()
    })

    it('leaves a login token the view stored before a full-page redirect', () => {
      hidePageWith(TokenType.Login)

      expect(mocks.stashToken).not.toHaveBeenCalled()
      expect(mocks.removeToken).not.toHaveBeenCalled()
    })

    it('does not bring back a token the view already removed from the cookies', () => {
      hidePageWith(undefined, TokenType.PasswordResetRequired)

      expect(mocks.stashToken).not.toHaveBeenCalled()
    })

    it('ends the flow when the page comes back from the back/forward cache', () => {
      useClearTokenOnLeave(VIEW_TYPES)

      mocks.listeners.pageshow({ persisted: false })
      expect(mocks.discardStashedToken).not.toHaveBeenCalled()
      expect(mocks.routerGo).not.toHaveBeenCalled()

      mocks.listeners.pageshow({ persisted: true })
      expect(mocks.discardStashedToken).toHaveBeenCalledOnce()
      expect(mocks.routerGo).toHaveBeenCalledWith(0)
    })
  })
})
