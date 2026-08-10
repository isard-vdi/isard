import { afterEach, describe, expect, it, vi } from 'vitest'
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

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() })
}))

vi.mock('@/lib/auth', () => ({
  parseToken: () => undefined,
  isLoginClaims: () => false,
  useCookies: () => ({}),
  setToken: vi.fn(),
  checkLoginRegister: vi.fn(),
  getToken: () => undefined,
  getBearer: () => ''
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ setUser: vi.fn(), user: undefined })
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
})
