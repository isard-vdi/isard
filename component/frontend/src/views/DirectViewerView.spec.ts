import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed, type Ref } from 'vue'

// ── Reactive test state driving the mocked queries ──────────────────────────
const viewerData: Ref<any> = ref(null)
const viewerError: Ref<any> = ref(null)
const viewerPending = ref(false)
const loginConfig: Ref<any> = ref(null)
const desktopDetails: Ref<any> = ref(null)

// Controllable outputs of the mocked @/lib/desktops helpers.
const bookingText: Ref<string | null> = ref(null)
const mainButtonAction = ref<string>('none')

const cookieSetMock = vi.fn()
const connectMock = vi.fn()
const clientSetConfigMock = vi.fn()
const refetchMock = vi.fn()
// useMutation is called twice in the view (resetDesktop, then startDesktop);
// capture each returned mutate in order.
const mutations: { mutate: ReturnType<typeof vi.fn> }[] = []

let useQueryCallIndex = 0

vi.mock('@tanstack/vue-query', () => {
  const useQuery = () => {
    const idx = useQueryCallIndex
    useQueryCallIndex += 1
    // Order matches DirectViewerView.vue: (0) desktopViewer, (1) loginConfig,
    // (2) desktopDetails.
    if (idx === 0)
      return {
        data: viewerData,
        error: viewerError,
        isError: computed(() => viewerError.value != null),
        isPending: viewerPending
      }
    if (idx === 1) return { data: loginConfig, error: ref(null), isPending: ref(false) }
    return { data: desktopDetails, error: ref(null), isPending: ref(false), refetch: refetchMock }
  }
  const useQueryClient = () => ({ setQueryData: vi.fn(), invalidateQueries: vi.fn() })
  const useMutation = () => {
    const mutate = vi.fn()
    mutations.push({ mutate })
    return { mutate, isPending: ref(false) }
  }
  return { useQuery, useQueryClient, useMutation }
})

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  getDesktopViewerByTokenOptions: () => ({ queryKey: { _id: 'viewer' } }),
  getDesktopViewerByTokenQueryKey: () => ({ _id: 'viewer' }),
  apiV4LoginConfigOptions: () => ({ queryKey: { _id: 'login' } })
}))

vi.mock('@/gen/oas/apiv4', () => ({
  resetDesktop: vi.fn(async () => ({ data: {}, error: null }))
}))

vi.mock('@/gen/oas/apiv4/types.gen', () => ({
  DesktopStatusEnum: {
    UNKNOWN: 'Unknown',
    STARTED: 'Started',
    STARTING: 'Starting',
    WAITING_IP: 'WaitingIP'
  }
}))

// Isolated apiv4 client the view builds with createClient(createConfig()).
vi.mock('@/gen/oas/apiv4/client', () => ({
  createConfig: () => ({}),
  createClient: () => ({
    setConfig: clientSetConfigMock,
    get: vi.fn(async () => ({ data: null, error: null })),
    put: vi.fn(async () => ({ data: null, error: null }))
  })
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: 'tok-1' } })
}))

// The view destructures { t, d } from useI18n. `d` must exist; `t` serialises
// its params so assertions can look for the key.
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) =>
      params && Object.keys(params).length ? `${k}::${JSON.stringify(params)}` : k,
    d: (_date: Date, opts?: Record<string, unknown>) =>
      opts?.dateStyle ? 'DATE' : opts?.timeStyle ? 'TIME' : 'D',
    locale: ref('en-US')
  }),
  // @/lib/i18n.ts (pulled in transitively) calls createI18n at module load and
  // reads i18n.global.{locale.value,t}.
  createI18n: () => ({
    global: { locale: { value: 'en-US' }, t: (k: string) => k }
  })
}))

vi.mock('@vueuse/integrations/useCookies', () => ({
  useCookies: () => ({ set: cookieSetMock })
}))

vi.mock('@/services/directViewerSocket', () => ({
  useDirectViewerSocket: () => ({ isConnected: ref(false), connect: connectMock })
}))

// @/lib/desktops — booking-notification text and the main-button action are
// controlled per-test via the refs above.
vi.mock('@/lib/desktops', () => ({
  desktopBookingNotificationText: () => bookingText.value,
  desktopActionsData: () => ({
    actionButton: {
      action: mainButtonAction.value,
      hierarchy: 'primary',
      icon: '',
      iconClass: '',
      label: 'action'
    }
  }),
  DesktopActionsEnum: { Reset: 'reset', Stop: 'stop', Start: 'start' }
}))

// ── Child-component stubs ───────────────────────────────────────────────────
// The desktop-card barrel transitively pulls DirectViewerCardPreview → NoVNC.vue
// → @novnc/novnc (whose 1.6 package has no resolvable entry under vitest), so
// stub every symbol the view imports from it. DesktopCardBase renders its slots
// so the header/footer/viewer buttons are assertable.
vi.mock('@/components/desktop-card', () => ({
  DesktopCardBase: {
    template:
      '<div data-test="card-base">' +
      '<slot name="image" /><slot name="header-actions" /><slot name="ip" />' +
      '<slot name="overlay" /><slot name="header" /><slot name="footer" />' +
      '</div>'
  },
  DesktopCardHeader: {
    props: ['notificationText', 'name', 'description'],
    template:
      '<div data-test="card-header" :data-notification="notificationText ?? \'\'">{{ name }}</div>'
  },
  DesktopCardFooter: {
    props: ['mainButtonData', 'desktopStatus', 'desktopViewers', 'desktopIp', 'preferredViewer'],
    emits: ['mainButtonClick'],
    template: '<button data-test="footer-main" @click="$emit(\'mainButtonClick\')">main</button>'
  },
  DesktopCardIp: { template: '<div data-test="card-ip" />' },
  DesktopCardNetworksOverlay: {
    emits: ['showNetworksModal'],
    template: '<div data-test="card-networks" @click="$emit(\'showNetworksModal\')" />'
  },
  DesktopCardBastionOverlay: { template: '<div data-test="card-bastion" />' },
  DesktopCardSkeleton: { template: '<div data-test="desktop-card-skeleton" />' },
  DesktopCardOverlayButton: {
    props: ['icon', 'title', 'active', 'activeLabel', 'ariaLabel'],
    emits: ['click'],
    template:
      '<button data-test="overlay-btn" :data-icon="icon" :aria-label="ariaLabel" @click="$emit(\'click\')" />'
  }
}))

vi.mock('@/components/desktops', () => ({
  DesktopBastionInfoModal: {
    props: ['open', 'desktopId', 'desktopName', 'bastion'],
    emits: ['close'],
    template: '<div data-test="bastion-modal" :data-open="String(open)" />'
  },
  DesktopNetworksModal: {
    props: [
      'open',
      'desktopId',
      'desktopName',
      'desktopStatus',
      'directViewerToken',
      'directViewerClient'
    ],
    emits: ['close'],
    template: '<div data-test="networks-modal" :data-open="String(open)" />'
  }
}))

vi.mock('@/components/desktop-card/parts/DirectViewerCardPreview.vue', () => ({
  default: { template: '<div data-test="card-preview" />' }
}))

vi.mock('@/components/domain/DomainAccessSummary.vue', () => ({
  default: { template: '<div data-test="access-summary" />' }
}))
vi.mock('@/components/domain/DomainHardwareSummary.vue', () => ({
  default: { template: '<div data-test="hardware-summary" />' }
}))

vi.mock('@/components/login', () => ({
  LoginNotification: {
    props: ['config'],
    template:
      '<div data-test="login-notification">{{ config?.title }} {{ config?.description }}</div>'
  }
}))

vi.mock('@/components/modal', () => ({
  AlertModal: {
    props: ['open', 'level', 'size', 'title', 'description', 'loading'],
    emits: ['update:open'],
    template: '<div data-test="reset-modal" :data-open="String(open)"><slot name="footer" /></div>'
  },
  ChangeViewerModal: {
    props: ['open', 'availableViewerIds', 'currentViewerId'],
    emits: ['close', 'change'],
    template: '<div data-test="change-viewer-modal" :data-open="String(open)" />'
  }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['hierarchy', 'size', 'icon', 'iconClass', 'iconStrokeColor', 'disabled', 'ariaLabel'],
    emits: ['click'],
    template:
      '<button data-test="btn" :aria-label="ariaLabel" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))
vi.mock('@/components/ui/button-group', () => ({
  ButtonGroup: { template: '<div data-test="button-group"><slot /></div>' },
  ButtonGroupSeparator: { template: '<span data-test="btn-group-sep" />' }
}))
vi.mock('@/components/ui/separator/Separator.vue', () => ({
  default: { template: '<hr data-test="separator" />' }
}))
vi.mock('@/components/icon', () => ({
  Icon: { template: '<span data-test="icon" />' }
}))

import DirectViewerView from './DirectViewerView.vue'

const startedDesktop = (overrides: Record<string, unknown> = {}) => ({
  jwt: 'tok-jwt',
  id: 'desktop-id',
  name: 'My Desktop',
  status: 'Started',
  description: '',
  image: { url: '' },
  viewers: {},
  ...overrides
})

const mountView = () => mount(DirectViewerView)

describe('DirectViewerView', () => {
  beforeEach(() => {
    viewerData.value = null
    viewerError.value = null
    viewerPending.value = false
    loginConfig.value = null
    desktopDetails.value = null
    bookingText.value = null
    mainButtonAction.value = 'none'
    cookieSetMock.mockReset()
    connectMock.mockReset()
    clientSetConfigMock.mockReset()
    refetchMock.mockReset()
    mutations.length = 0
    useQueryCallIndex = 0
  })

  afterEach(() => {
    document.body.replaceChildren()
  })

  it('renders the loading skeleton while the viewer query is pending', () => {
    viewerPending.value = true
    const wrapper = mountView()
    expect(wrapper.find('[data-test="desktop-card-skeleton"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('views.direct-viewer.connecting-to')
  })

  it('renders the generic error box when the viewer query errors without a code', async () => {
    viewerError.value = {}
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('views.direct-viewer.error-title')
    expect(wrapper.text()).toContain('views.direct-viewer.error-description')
  })

  it('renders the not-booked error variant for description_code desktop_not_booked', async () => {
    viewerError.value = { description_code: 'desktop_not_booked' }
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('views.direct-viewer.errors.not-booked.title')
    expect(wrapper.text()).not.toContain('views.direct-viewer.error-title')
  })

  it('renders the desktop name once the viewer data resolves', async () => {
    viewerData.value = startedDesktop({ name: 'Ubuntu Lab' })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('views.direct-viewer.connecting-to')
    expect(wrapper.text()).toContain('Ubuntu Lab')
  })

  it('stores the viewerToken cookie and connects the socket when the jwt resolves', async () => {
    const wrapper = mountView()
    viewerData.value = startedDesktop({ jwt: 'resolved-jwt' })
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(cookieSetMock).toHaveBeenCalledWith(
      'viewerToken',
      'resolved-jwt',
      expect.objectContaining({ path: '/', sameSite: 'strict' })
    )
    expect(connectMock).toHaveBeenCalledWith('resolved-jwt')
  })

  it('feeds the scheduled-shutdown notification text into the card header', async () => {
    viewerData.value = startedDesktop({ scheduled: { shutdown: '2026-04-25T20:00:00Z' } })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('[data-test="card-header"]').attributes('data-notification')).toContain(
      'notification-bar.shutdown'
    )
  })

  it('prefers the booking notification text over the shutdown text', async () => {
    bookingText.value = 'BOOKING-NOTICE'
    viewerData.value = startedDesktop({ scheduled: { shutdown: '2026-04-25T20:00:00Z' } })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('[data-test="card-header"]').attributes('data-notification')).toBe(
      'BOOKING-NOTICE'
    )
  })

  it('renders the login notification cover when loginConfig enables it', async () => {
    loginConfig.value = {
      notification_cover: { enabled: true, title: 'Outage', description: 'Maintenance in progress' }
    }
    viewerData.value = startedDesktop()
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Outage')
    expect(wrapper.text()).toContain('Maintenance in progress')
  })

  it('opens the reset modal on the main action and calls resetDesktop on confirm', async () => {
    mainButtonAction.value = 'reset'
    viewerData.value = startedDesktop()
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="reset-modal"]').attributes('data-open')).toBe('false')
    await wrapper.find('[data-test="footer-main"]').trigger('click')
    expect(wrapper.find('[data-test="reset-modal"]').attributes('data-open')).toBe('true')

    // Footer slot renders [cancel, confirm]; confirm calls the reset mutation.
    const modalButtons = wrapper.find('[data-test="reset-modal"]').findAll('[data-test="btn"]')
    expect(modalButtons.length).toBe(2)
    await modalButtons[1].trigger('click')
    expect(mutations[0].mutate).toHaveBeenCalled()
  })

  it('shows the viewer button group and opens the change-viewer modal for multiple viewers', async () => {
    viewerData.value = startedDesktop({
      viewers: {
        'browser-vnc': { kind: 'browser', viewer: '/viewer/vnc' },
        'file-spice': { kind: 'file' },
        empty: null
      }
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="button-group"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="change-viewer-modal"]').attributes('data-open')).toBe('false')

    const settings = wrapper.find('[aria-label="views.direct-viewer.select-viewer"]')
    expect(settings.exists()).toBe(true)
    await settings.trigger('click')
    expect(wrapper.find('[data-test="change-viewer-modal"]').attributes('data-open')).toBe('true')
  })

  it('opens a browser viewer in a new tab with the direct flag set', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    viewerData.value = startedDesktop({
      viewers: { 'browser-vnc': { kind: 'browser', cookie: 'ck', viewer: '/viewer/vnc' } }
    })
    const wrapper = mountView()
    await flushPromises()

    // The active-viewer button is the first button inside the group (no aria-label).
    const groupButtons = wrapper.find('[data-test="button-group"]').findAll('[data-test="btn"]')
    await groupButtons[0].trigger('click')

    expect(cookieSetMock).toHaveBeenCalledWith(
      'browser_viewer',
      'ck',
      expect.objectContaining({ path: '/' })
    )
    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(openSpy.mock.calls[0][0]).toContain('direct=1')
    vi.unstubAllGlobals()
  })

  it('opens the networks modal from the networks overlay overflow', async () => {
    viewerData.value = startedDesktop()
    const wrapper = mountView()
    await flushPromises()

    // Modal is closed (not rendered) until requested.
    expect(wrapper.find('[data-test="networks-modal"]').exists()).toBe(false)

    // Toggle the networks overlay via its header button (modem-02 icon).
    const networksBtn = wrapper.find('[data-test="overlay-btn"][data-icon="modem-02"]')
    expect(networksBtn.exists()).toBe(true)
    await networksBtn.trigger('click')

    // The overlay's +N overflow emits show-networks-modal, opening the modal.
    const overlay = wrapper.find('[data-test="card-networks"]')
    expect(overlay.exists()).toBe(true)
    await overlay.trigger('click')

    expect(wrapper.find('[data-test="networks-modal"]').attributes('data-open')).toBe('true')
  })

  it('refetches the desktop details when the viewer status changes', async () => {
    viewerData.value = startedDesktop({ status: 'WaitingIP' })
    mountView()
    await flushPromises()
    refetchMock.mockClear()

    // Socket flips the desktop to Started → details (holding the IP) refetch.
    viewerData.value = { ...viewerData.value, status: 'Started' }
    await flushPromises()

    expect(refetchMock).toHaveBeenCalled()
  })
})
