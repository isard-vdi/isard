import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { ref, type Ref } from 'vue'

enableAutoUnmount(afterEach)

const viewerData: Ref<unknown> = ref(null)
const viewerError: Ref<unknown> = ref(null)
const viewerPending = ref(false)
const loginConfig: Ref<unknown> = ref(null)
const viewerDocs: Ref<unknown> = ref(null)
const setQueryDataMock = vi.fn()
const cookieSetMock = vi.fn()
const ioMock = vi.fn()

let useQueryCallIndex = 0

vi.mock('@tanstack/vue-query', () => {
  const useQuery = () => {
    const idx = useQueryCallIndex
    useQueryCallIndex += 1
    if (idx === 0) return { data: viewerData, error: viewerError, isPending: viewerPending }
    if (idx === 1) return { data: viewerDocs, error: ref(null), isPending: ref(false) }
    return { data: loginConfig, error: ref(null), isPending: ref(false) }
  }
  const useQueryClient = () => ({ setQueryData: setQueryDataMock })
  return { useQuery, useQueryClient }
})

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  getDesktopViewerByTokenOptions: () => ({
    queryKey: { _id: 'viewer' }
  }),
  getDesktopViewerByTokenQueryKey: () => ({ _id: 'viewer' }),
  getViewerDocsOptions: () => ({ queryKey: { _id: 'docs' } }),
  apiV4LoginConfigOptions: () => ({ queryKey: { _id: 'login' } })
}))

vi.mock('@/gen/oas/apiv4', () => ({
  DesktopStatusEnum: { WAITING_IP: 'WaitingIP' }
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: 'tok-1' } })
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) => {
      if (params && Object.keys(params).length) {
        return `${k}::${JSON.stringify(params)}`
      }
      return k
    },
    locale: ref('en-US')
  })
}))

vi.mock('socket.io-client', () => ({
  io: (...args: unknown[]) => {
    ioMock(...args)
    return { on: vi.fn(), connect: vi.fn(), disconnect: vi.fn() }
  }
}))

vi.mock('@vueuse/integrations/useCookies', () => ({
  useCookies: () => ({ set: cookieSetMock })
}))

vi.mock('@/lib/constants', () => ({ webSockets: '/ws' }))

vi.mock('@/lib/booking/date-utils', () => ({
  formatAsTime: (s: string) => `time(${s})`,
  utcToLocalTime: (s: string) => `local(${s})`
}))

vi.mock('@/components/direct-viewer', () => ({
  DirectViewerButton: {
    props: ['viewer', 'state', 'description', 'token'],
    emits: ['help'],
    template:
      '<div class="dvb" :data-kind="viewer.kind" :data-protocol="viewer.protocol">' +
      '<button class="help" @click="$emit(\'help\', viewer.protocol)">help</button>' +
      '</div>'
  },
  DirectViewerHelpRDP: {
    props: ['open', 'documentationUrl'],
    template: '<div data-test="help-rdp" :data-open="open" />'
  },
  DirectViewerHelpSpice: {
    props: ['open', 'documentationUrl'],
    template: '<div data-test="help-spice" :data-open="open" />'
  },
  DirectViewerResetModal: {
    props: ['open', 'token'],
    template: '<div data-test="reset" :data-open="open" />'
  },
  DirectViewerSkeleton: {
    template: '<div data-test="skeleton" />'
  }
}))

vi.mock('@/components/ui/spinner', () => ({
  Spinner: { template: '<span data-test="spinner" />' }
}))
vi.mock('@/components/ui/alert', () => ({
  Alert: { template: '<div data-test="alert"><slot /></div>' },
  AlertDescription: { template: '<div data-test="alert-desc"><slot /></div>' },
  AlertTitle: { template: '<div data-test="alert-title"><slot /></div>' }
}))
vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['hierarchy', 'size'],
    emits: ['click'],
    template: '<button data-test="btn" @click="$emit(\'click\')"><slot /></button>'
  }
}))
vi.mock('@/components/icon', () => ({
  Icon: { template: '<span data-test="icon" />' }
}))

import DirectViewerView from './DirectViewerView.vue'

const mountView = () =>
  mount(DirectViewerView, {
    global: {
      stubs: {
        'i18n-t': {
          props: ['keypath'],
          template: '<span data-test="i18n-t">{{ keypath }}</span>'
        }
      }
    }
  })

describe('DirectViewerView', () => {
  beforeEach(() => {
    viewerData.value = null
    viewerError.value = null
    viewerPending.value = false
    loginConfig.value = null
    viewerDocs.value = null
    setQueryDataMock.mockReset()
    cookieSetMock.mockReset()
    ioMock.mockReset()
    useQueryCallIndex = 0
  })

  afterEach(() => {
    document.body.replaceChildren()
  })

  it('renders the loading spinner while pending and no name yet', () => {
    viewerPending.value = true
    const wrapper = mountView()
    expect(wrapper.text()).toContain('views.direct-viewer.loading')
    expect(wrapper.findAll('[data-test="skeleton"]').length).toBe(2)
  })

  it('renders fallback error text when description_code is missing', async () => {
    viewerError.value = {}
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('views.direct-viewer.errors.not_found')
  })

  it('formats the desktop_not_booked_until error with localized start time', async () => {
    viewerError.value = {
      description_code: 'desktop_not_booked_until',
      params: { start: '2026-04-25T10:00:00Z' }
    }
    const wrapper = mountView()
    await flushPromises()
    const errKey = 'views.direct-viewer.errors.desktop_not_booked_until'
    expect(wrapper.text()).toContain(errKey)
    expect(wrapper.text()).toContain('local(2026-04-25T10:00:00Z)')
  })

  it('renders generic description_code errors with their params', async () => {
    viewerError.value = {
      description_code: 'desktop_not_started',
      params: { foo: 'bar' }
    }
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('views.direct-viewer.errors.desktop_not_started')
  })

  it('opens the websocket and stores the cookie when viewer data resolves', async () => {
    const wrapper = mountView()
    viewerData.value = {
      jwt: 'tok-jwt',
      id: 'desktop-id',
      name: 'My Desktop',
      status: 'Started',
      viewers: {
        'browser-vnc': { kind: 'browser', protocol: 'vnc' },
        'file-spice': { kind: 'file', protocol: 'spice' },
        empty: null
      }
    }
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(cookieSetMock).toHaveBeenCalledWith(
      'viewerToken',
      'tok-jwt',
      expect.objectContaining({ path: '/', sameSite: 'strict' })
    )
    expect(ioMock).toHaveBeenCalledTimes(1)
    const ioArgs = ioMock.mock.calls[0]
    expect(ioArgs[0]).toBe('/userspace')
    expect(ioArgs[1].query).toEqual({ room: 'desktop-id' })
  })

  it('splits browser viewers and file viewers into separate sections', async () => {
    const wrapper = mountView()
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'd1',
      status: 'Started',
      viewers: {
        'browser-vnc': { kind: 'browser', protocol: 'vnc' },
        'browser-rdp': { kind: 'browser', protocol: 'rdp' },
        'file-spice': { kind: 'file', protocol: 'spice' },
        'file-rdpgw': { kind: 'file', protocol: 'rdpgw' },
        empty: null
      }
    }
    await flushPromises()

    const cards = wrapper.findAll('.dvb')
    expect(cards.length).toBe(4)
    const kinds = cards.map((c) => c.attributes('data-kind'))
    expect(kinds.filter((k) => k === 'browser').length).toBe(2)
    expect(kinds.filter((k) => k === 'file').length).toBe(2)
  })

  it('renders shutdownText only when scheduled.shutdown is set', async () => {
    const wrapper = mountView()
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'My Desktop',
      status: 'Started',
      viewers: {},
      scheduled: { shutdown: '2026-04-25T20:00:00Z' }
    }
    await flushPromises()
    expect(wrapper.text()).toContain('components.message-modal.messages.desktop-time-limit')
    expect(wrapper.text()).toContain('time(local(2026-04-25T20:00:00Z))')
  })

  it('renders the notification cover banner when loginConfig provides one', async () => {
    loginConfig.value = {
      notification_cover: {
        enabled: true,
        title: 'Outage',
        description: 'Maintenance in progress'
      }
    }
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'd1',
      status: 'Started',
      viewers: {}
    }
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Outage')
    expect(wrapper.text()).toContain('Maintenance in progress')
  })

  it('opens the reset modal when the restart button is clicked', async () => {
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'd1',
      status: 'Started',
      viewers: {}
    }
    const wrapper = mountView()
    await flushPromises()

    const restart = wrapper.findAll('[data-test="btn"]')[0]
    expect(restart).toBeTruthy()
    await restart.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="reset"]').attributes('data-open')).toBe('true')
  })

  it('opens the spice help modal when a button emits help with spice', async () => {
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'd1',
      status: 'Started',
      viewers: { 'file-spice': { kind: 'file', protocol: 'spice' } }
    }
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.dvb .help').trigger('click')
    expect(wrapper.find('[data-test="help-spice"]').attributes('data-open')).toBe('true')
    expect(wrapper.find('[data-test="help-rdp"]').attributes('data-open')).toBe('false')
  })

  it('opens the rdp help modal when a button emits help with rdpgw', async () => {
    viewerData.value = {
      jwt: 'jwt',
      id: 'd1',
      name: 'd1',
      status: 'Started',
      viewers: { 'file-rdpgw': { kind: 'file', protocol: 'rdpgw' } }
    }
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.dvb .help').trigger('click')
    expect(wrapper.find('[data-test="help-rdp"]').attributes('data-open')).toBe('true')
    expect(wrapper.find('[data-test="help-spice"]').attributes('data-open')).toBe('false')
  })
})
