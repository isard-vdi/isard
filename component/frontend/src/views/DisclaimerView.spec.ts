import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

// The disclaimer body and footer are admin-authored HTML served by apiv4 and
// painted with v-html. An admin who can edit the template can therefore ship
// script to every user who has not accepted yet — the same hole this MR closes
// in the Vue 2 disclaimer page.
const BODY = '<p>legal <b>bold</b></p><script>window.__pwned = 1</script>'
const FOOTER = '<span>footer</span><img src="x" onerror="window.__pwned = 2">'

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k })
}))

// Shared spies so a test can assert the ORDER of the calls the accept flow
// makes: the store has to learn the new token before the router navigates, or
// the guard reads a stale token type and bounces back here.
const mocks = vi.hoisted(() => ({
  order: [] as string[],
  push: vi.fn(),
  storeSetToken: vi.fn(),
  parseToken: vi.fn(),
  isLoginClaims: vi.fn(),
  checkLoginRegister: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn() })
}))

vi.mock('@/lib/auth', () => ({
  parseToken: mocks.parseToken,
  isLoginClaims: mocks.isLoginClaims,
  useCookies: () => ({}),
  setToken: vi.fn(),
  checkLoginRegister: mocks.checkLoginRegister,
  getToken: () => undefined,
  getBearer: () => ''
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    setToken: mocks.storeSetToken,
    logout: vi.fn(),
    setUser: vi.fn(),
    user: undefined
  })
}))

vi.mock('@/gen/oas/authentication', () => ({
  acknowledgeDisclaimer: vi.fn(),
  login: vi.fn()
}))

// The generated client is produced by codegen, so the query options are stubbed
// rather than driven through it: what is under test is what the view paints,
// not how it fetches.
vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  apiV4DisclaimerOptions: () => ({
    queryKey: ['disclaimer'],
    queryFn: async () => ({ title: 'Disclaimer', body: BODY, footer: FOOTER })
  })
}))

import { acknowledgeDisclaimer, login } from '@/gen/oas/authentication'

import DisclaimerView from './DisclaimerView.vue'

const mountView = async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  })
  const wrapper = mount(DisclaimerView, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] }
  })
  await flushPromises()
  return wrapper
}

describe('DisclaimerView', () => {
  beforeEach(() => {
    mocks.order.length = 0
    mocks.push.mockImplementation(() => {
      mocks.order.push('router.push')
    })
    mocks.storeSetToken.mockImplementation(() => {
      mocks.order.push('store.setToken')
    })
    mocks.parseToken.mockReturnValue(undefined)
    mocks.isLoginClaims.mockReturnValue(false)
    mocks.checkLoginRegister.mockReturnValue(undefined)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('strips the script from an admin-authored disclaimer body', async () => {
    const html = (await mountView()).html()
    expect(html).not.toContain('<script')
    expect(html).not.toContain('__pwned')
    // the legitimate markup survives: this sanitizes, it does not escape
    expect(html).toContain('<b>bold</b>')
  })

  it('strips the event handler from the footer', async () => {
    const html = (await mountView()).html()
    expect(html).not.toContain('onerror')
    expect(html).toContain('<span>footer</span>')
  })

  it('hands the new token to the auth store before navigating to the notifications page', async () => {
    const bearer = 'the.login.token'
    mocks.parseToken.mockReturnValue({
      type: 'login',
      iat: Math.floor(Date.now() / 1000),
      session_id: 'session-1',
      data: { role_id: 'user' }
    })
    mocks.isLoginClaims.mockReturnValue(true)

    vi.mocked(acknowledgeDisclaimer).mockResolvedValue({ error: undefined } as never)
    vi.mocked(login).mockResolvedValue({
      error: undefined,
      response: {
        headers: new Headers({
          authorization: `Bearer ${bearer}`,
          location: '/notifications/login'
        })
      }
    } as never)

    const wrapper = await mountView()
    await wrapper.find('button[data-slot="button"]:last-of-type').trigger('click')
    await flushPromises()

    // A stale store here is what sent the user back to the disclaimer, so the
    // token has to land before the navigation, not merely alongside it.
    expect(mocks.order).toEqual(['store.setToken', 'router.push'])
    expect(mocks.storeSetToken).toHaveBeenCalledWith(bearer)
    expect(mocks.push).toHaveBeenCalledWith('/notifications/login')
  })
})
