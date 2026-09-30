import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TokenType } from '@/lib/auth'

const mocks = vi.hoisted(() => ({
  leaveGuard: undefined as (() => unknown) | undefined,
  store: { tokenType: undefined as string | undefined, logout: vi.fn() }
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (guard: () => unknown) => {
    mocks.leaveGuard = guard
  }
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => mocks.store
}))

import { useClearTokenOnLeave } from './useClearTokenOnLeave'

const leaveWith = (tokenType: string | undefined) => {
  mocks.store.tokenType = tokenType
  useClearTokenOnLeave([TokenType.PasswordResetRequired, TokenType.PasswordReset])
  mocks.leaveGuard?.()
}

describe('useClearTokenOnLeave', () => {
  beforeEach(() => {
    mocks.leaveGuard = undefined
    mocks.store.logout.mockClear()
  })

  it.each([TokenType.PasswordResetRequired, TokenType.PasswordReset])(
    'logs out when leaving with the view token %s still stored',
    (tokenType) => {
      leaveWith(tokenType)
      expect(mocks.store.logout).toHaveBeenCalledOnce()
    }
  )

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
