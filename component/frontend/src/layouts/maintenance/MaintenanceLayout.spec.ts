import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (key: string) => key })
}))

let token: string | undefined = 'a.token'
const removeToken = vi.fn(() => {
  token = undefined
})
vi.mock('@/lib/auth', () => ({
  getToken: () => token,
  removeToken: () => removeToken(),
  useCookies: () => ({})
}))

vi.mock('@/components/locale-switch', () => ({
  LocaleSwitch: { template: '<div />' }
}))

import MaintenanceLayout from './MaintenanceLayout.vue'

describe('MaintenanceLayout', () => {
  beforeEach(() => {
    token = 'a.token'
    vi.clearAllMocks()
  })

  // Regression: the button used to only clear the cookie when a session was
  // present, so an authenticated user had to click it twice to reach /login.
  it('goes to login on the first click of an authenticated session', async () => {
    const wrapper = mount(MaintenanceLayout)

    await wrapper.get('button').trigger('click')

    expect(removeToken).toHaveBeenCalledOnce()
    expect(push).toHaveBeenCalledWith({ name: 'login' })
  })

  it('goes to login without a session', async () => {
    token = undefined
    const wrapper = mount(MaintenanceLayout)

    await wrapper.get('button').trigger('click')

    expect(removeToken).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith({ name: 'login' })
  })
})
