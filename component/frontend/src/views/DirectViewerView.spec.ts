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
const setQueryDataMock = vi.fn()
const renewMock = vi.fn()
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
    return { data: desktopDetails, error: ref(null), isPending: ref(false) }
  }
  const useQueryClient = () => ({
    setQueryData: setQueryDataMock,
    invalidateQueries: vi.fn()
  })
  const useMutation = (options?: any) => {
    const mutate = vi.fn()
    // `mutateAsync` runs the real mutationFn + onSuccess so the token-renewal
    // wiring can be asserted end to end.
    const mutateAsync = vi.fn(async (vars?: unknown) => {
      const result = await options?.mutationFn?.(vars)
      await options?.onSuccess?.(result, vars)
      return result
    })
    mutations.push({ mutate })
    return { mutate, mutateAsync, isPending: ref(false) }
  }
  return { useQuery, useQueryClient, useMutation }
})

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  getDesktopViewerByTokenOptions: () => ({ queryKey: { _id: 'viewer' } }),
  getDesktopViewerByTokenQueryKey: () => ({ _id: 'viewer' }),
  getDesktopDetailsFromTokenOptions: () => ({ queryKey: { _id: 'details' } }),
  startDesktopFromTokenMutation: () => ({ mutationFn: vi.fn() }),
  resetDesktopMutation: () => ({ mutationFn: vi.fn() }),
  apiV4LoginConfigOptions: () => ({ queryKey: { _id: 'login' } })
}))

vi.mock('@/gen/oas/apiv4', () => ({
  // Wrapped so the factory doesn't touch `renewMock` before it is initialised.
  renewDesktopViewerByToken: (...args: unknown[]) => renewMock(...args)
}))

// `exp` in the past for `expiring-jwt`, an hour out for anything else.
vi.mock('jwt-decode', () => ({
  jwtDecode: (jwt: string) =>
    jwt === 'expiring-jwt' ? { exp: 1 } : { exp: Math.floor(Date.now() / 1000) + 3600 }
}))

vi.mock('@/gen/oas/apiv4/types.gen', () => ({
  DesktopStatusEnum: {
    UNKNOWN: 'Unknown',
    STARTED: 'Started',
    STARTING: 'Starting',
    STOPPED: 'Stopped',
    STOPPING: 'Stopping',
    SHUTTING_DOWN: 'Shutting-down',
    SUSPENDED: 'Suspended',
    RESETTING: 'Resetting',
    FAILED: 'Failed',
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
  desktopActionsData: (status: string) => ({
    actionButton: {
      action: mainButtonAction.value,
      hierarchy: 'primary',
      icon: '',
      iconClass: '',
      label: 'action'
    },
    // Mirrors the real helper: viewers only while the desktop is up.
    viewers: ['Started', 'WaitingIP', 'Shutting-down'].includes(status)
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
    props: ['desktopIp'],
    emits: ['showNetworksModal'],
    template:
      '<div data-test="card-networks" :data-ip="desktopIp" @click="$emit(\'showNetworksModal\')" />'
  },
  DesktopCardBastionOverlay: { template: '<div data-test="card-bastion" />' },
  DesktopCardInfoOverlay: {
    emits: ['showInfoModal'],
    template: '<div data-test="card-info" @click="$emit(\'showInfoModal\')" />'
  },
  DesktopCardOverlayButton: {
    props: ['icon', 'title', 'active', 'activeLabel', 'ariaLabel'],
    emits: ['click'],
    template:
      '<button data-test="overlay-btn" :data-icon="icon" :aria-label="ariaLabel" @click="$emit(\'click\')" />'
  },
  cardOverlayPaddingVariants: () => '',
  cardOverlayLabelVariants: () => ''
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
  },
  DomainInfoModal: {
    props: [
      'open',
      'isLoading',
      'domainId',
      'name',
      'description',
      'status',
      'ip',
      'vcpu',
      'ram',
      'bootOrder',
      'diskBus',
      'vga',
      'viewers',
      'fullscreen',
      'isos',
      'floppies',
      'reservables',
      'credentials',
      'kind',
      'template',
      'desktopKind',
      'items'
    ],
    emits: ['close'],
    template: '<div data-test="info-modal" :data-open="String(open)" />'
  }
}))

vi.mock('@/components/desktop-card/parts/DirectViewerCardPreview.vue', () => ({
  default: { template: '<div data-test="card-preview" />' }
}))

vi.mock('@/components/domain/DomainSummary.vue', () => ({
  default: { template: '<div data-test="domain-summary" />' }
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
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: { template: '<div data-test="tooltip"><slot /></div>' },
  TooltipTrigger: { props: ['asChild'], template: '<div><slot /></div>' },
  TooltipContent: { props: ['title'], template: '<div :data-title="title" />' },
  TooltipProvider: { template: '<div><slot /></div>' }
}))
vi.mock('@/components/icon', () => ({
  Icon: { template: '<span data-test="icon" />' }
}))
vi.mock('@/components/ui/spinner', () => ({
  Spinner: { props: ['size'], template: '<span data-test="spinner" />' }
}))
vi.mock('@/components/direct-viewer', () => ({
  DirectViewerLoadingHint: { template: '<p data-test="loading-hint" />' }
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
    setQueryDataMock.mockReset()
    renewMock.mockReset()
    mutations.length = 0
    useQueryCallIndex = 0
  })

  afterEach(() => {
    document.body.replaceChildren()
  })

  it('renders the loading state with the rotating hint while the viewer query is pending', () => {
    viewerPending.value = true
    const wrapper = mountView()
    expect(wrapper.find('[data-test="spinner"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="loading-hint"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('views.direct-viewer.loading.title')
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
    // The socket gets a getter, not the string: a renewed token has to reach
    // every reconnect handshake.
    const getJwt = connectMock.mock.calls.at(-1)![0]
    expect(typeof getJwt).toBe('function')
    expect(getJwt()).toBe('resolved-jwt')
  })

  it('renews the viewer jwt when it is about to expire', async () => {
    renewMock.mockResolvedValue({
      data: startedDesktop({ jwt: 'renewed-jwt', status: 'Started' })
    })
    viewerData.value = startedDesktop({ jwt: 'expiring-jwt' })
    mountView()
    await flushPromises()
    await vi.waitFor(() => expect(renewMock).toHaveBeenCalled())

    expect(renewMock.mock.calls[0][0]).toMatchObject({ path: { token: 'tok-1' } })
    // The fresh payload is written back onto the get-viewer cache entry, which
    // is what re-arms the client header, the cookie and the socket.
    await vi.waitFor(() => expect(setQueryDataMock).toHaveBeenCalled())
    const patch = setQueryDataMock.mock.calls[0][1]
    const merged = patch({ ...viewerData.value, status: 'Stopped' })
    expect(merged).toMatchObject({ jwt: 'renewed-jwt' })
    // renew-viewer reports a synthesised Started/WaitingIP; the live status wins.
    expect(merged.status).toBe('Stopped')
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
    // Declaration order in the view: [0] token renewal, [1] reset, [2] start.
    expect(mutations[1].mutate).toHaveBeenCalled()
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

    const settings = wrapper.find('[aria-label="components.change-viewer-modal.title"]')
    expect(settings.exists()).toBe(true)
    await settings.trigger('click')
    expect(wrapper.find('[data-test="change-viewer-modal"]').attributes('data-open')).toBe('true')
  })

  it.each(['Stopped', 'Maintenance'])(
    'hides the viewer button group when the desktop turns %s elsewhere',
    async (status) => {
      viewerData.value = startedDesktop({
        viewers: { 'browser-vnc': { kind: 'browser', viewer: '/viewer/vnc' } }
      })
      const wrapper = mountView()
      await flushPromises()
      expect(wrapper.find('[data-test="button-group"]').exists()).toBe(true)

      viewerData.value = { ...viewerData.value, status }
      await flushPromises()

      expect(wrapper.find('[data-test="button-group"]').exists()).toBe(false)
    }
  )

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

  it('opens the info domain modal from the info overlay', async () => {
    viewerData.value = startedDesktop()
    const wrapper = mountView()
    await flushPromises()

    // Modal is rendered (no v-if) but closed.
    expect(wrapper.find('[data-test="info-modal"]').attributes('data-open')).toBe('false')

    // Toggle the info overlay via its header button (info-circle icon).
    const infoBtn = wrapper.find('[data-test="overlay-btn"][data-icon="info-circle"]')
    expect(infoBtn.exists()).toBe(true)
    await infoBtn.trigger('click')

    // The overlay's "details" action emits show-info-modal
    const overlay = wrapper.find('[data-test="card-info"]')
    expect(overlay.exists()).toBe(true)
    await overlay.trigger('click')

    expect(wrapper.find('[data-test="info-modal"]').attributes('data-open')).toBe('true')
  })

  it('shows the guest IP straight off the viewer payload once the socket reports it', async () => {
    // The IP rides on get-viewer, so the socket patch is enough — no
    // get-details round trip is involved in surfacing it.
    viewerData.value = startedDesktop({ status: 'WaitingIP', ip: null })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-test="overlay-btn"][data-icon="modem-02"]').trigger('click')
    expect(wrapper.find('[data-test="card-networks"]').attributes('data-ip')).toBeUndefined()

    viewerData.value = { ...viewerData.value, status: 'Started', ip: '10.1.2.3' }
    await flushPromises()

    expect(wrapper.find('[data-test="card-networks"]').attributes('data-ip')).toBe('10.1.2.3')
  })
})
