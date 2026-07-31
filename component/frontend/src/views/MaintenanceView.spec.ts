import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

// No login token → the maintenanceStatus query is enabled; getBearer feeds the
// getMaintenance Authorization header.
vi.mock('@/lib/auth', () => ({
  getToken: () => undefined,
  getBearer: () => '',
  useCookies: () => ({})
}))

vi.mock('@/lib/i18n', () => ({
  Locale: {},
  setLocale: vi.fn()
}))

// Stub the layout so mounting doesn't pull the whole UI tree.
vi.mock('@/layouts/maintenance', () => ({
  MaintenanceLayout: { template: '<div data-test="maintenance-layout" />' }
}))

// Mock the generated HTTP client so the REAL generated query functions resolve
// without hitting the network. `getConfig` is needed by createQueryKey.
vi.mock('@/gen/oas/apiv4/client.gen', () => ({
  client: {
    get: vi.fn(async () => ({ data: { enabled: true, title: 't', body: 'b' }, error: undefined })),
    getConfig: () => ({ baseUrl: 'http://test' })
  }
}))

import MaintenanceView from './MaintenanceView.vue'

const mountView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  })
  const wrapper = mount(MaintenanceView, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] }
  })
  return { wrapper, queryClient }
}

describe('MaintenanceView', () => {
  afterEach(() => {
    document.body.replaceChildren()
    vi.clearAllMocks()
  })

  // Regression: each useQuery must receive a query KEY (the *QueryKey() array),
  // never the whole *Options() object. Passing *Options() as queryKey corrupts
  // the TanStack Query context and makes the generated queryFn crash with
  // "(destructured parameter) is undefined" during maintenance mode.
  it('registers every query with a valid array queryKey (not the *Options object)', async () => {
    const { wrapper, queryClient } = mountView()
    await flushPromises()

    const queries = queryClient.getQueryCache().getAll()
    // text + status + config fetch (maintenance is disabled without a token).
    expect(queries.length).toBeGreaterThanOrEqual(3)
    for (const query of queries) {
      expect(Array.isArray(query.queryKey)).toBe(true)
    }

    wrapper.unmount()
  })
})
