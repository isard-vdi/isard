import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import enUS from '@/locales/en-US.json'

const reRegisterBearer = 'header.rr.sig'

vi.mock('@/lib/auth', async () => {
  const actual = await vi.importActual<typeof import('@/lib/auth')>('@/lib/auth')
  return {
    ...actual,
    useCookies: () => ({}),
    getToken: () => ({
      type: actual.TokenType.ReRegister,
      provider: 'saml',
      category_id: 'default'
    }),
    getBearer: () => reRegisterBearer,
    setToken: vi.fn(),
    removeToken: vi.fn(),
    parseToken: (bearer: string) => ({
      type: actual.TokenType.ReRegister,
      provider: 'saml',
      category_id: 'default',
      bearer
    })
  }
})

vi.mock('@/lib/i18n', () => ({
  Locale: {},
  setLocale: vi.fn(),
  i18n: { global: { locale: { value: 'en-US' }, t: (k: string) => k } }
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() })
}))

vi.mock('@/layouts/login', () => ({
  LoginLayout: { template: '<div><slot /></div>' }
}))
vi.mock('@/components/register', () => ({
  RegisterForm: {
    template: '<button data-test="submit" @click="$emit(\'submit\', { code: \'x\' })" />'
  }
}))
vi.mock('@/components/login', () => ({
  Provider: {},
  LoginNotification: { template: '<div />' }
}))

vi.mock('@/gen/oas/apiv4/client.gen', () => ({
  client: {
    get: vi.fn(async () => ({ data: {}, error: undefined })),
    getConfig: () => ({ baseUrl: 'http://test' })
  }
}))

vi.mock('@/gen/oas/apiv4', async () => {
  const actual = await vi.importActual<typeof import('@/gen/oas/apiv4')>('@/gen/oas/apiv4')
  return {
    ...actual,
    registerUser: vi.fn(),
    reRegisterUser: vi.fn(async () => ({
      error: undefined,
      response: new Response(null, { status: 200 })
    }))
  }
})
vi.mock('@/gen/oas/authentication', async () => {
  const actual = await vi.importActual<typeof import('@/gen/oas/authentication')>(
    '@/gen/oas/authentication'
  )
  return {
    ...actual,
    login: vi.fn(async () => ({
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { authorization: `Bearer ${reRegisterBearer}` }
      })
    }))
  }
})

import RegisterView from './RegisterView.vue'

const mountView = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const i18n = createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': enUS } })
  return mount(RegisterView, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }], i18n],
      stubs: { RouterLink: true }
    }
  })
}

describe('RegisterView re-register hard block', () => {
  afterEach(() => {
    document.body.replaceChildren()
    vi.clearAllMocks()
  })

  it('shows the insufficient-code error when /login returns another re-register token', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-test="submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.text().toLowerCase()).toContain('valid code')
  })
})
