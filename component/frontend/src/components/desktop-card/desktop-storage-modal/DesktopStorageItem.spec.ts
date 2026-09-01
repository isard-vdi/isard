import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

const queryData = ref<unknown>(undefined)
const queryIsPending = ref(false)

vi.mock('@tanstack/vue-query', () => ({
  useQuery: () => ({ data: queryData, isPending: queryIsPending }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: ref(false) })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  getStorageOptions: () => ({}),
  getStorageQueryKey: () => [{}],
  getStorageTaskQueryKey: () => [{}],
  increaseStorageSizeMutation: () => ({})
}))

const userRef = ref<{ id: string; role_id: string } | null>({
  id: 'u-1',
  role_id: 'admin'
})

// Pinia setup stores auto-unwrap refs when accessed via the store
// object, so the mock exposes ``user`` via a getter that returns the
// raw value rather than the ref itself.
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get user() {
      return userRef.value
    }
  })
}))

vi.mock('@/gen/oas/apiv4', () => ({
  DesktopStatusEnum: {
    STARTED: 'Started',
    STOPPED: 'Stopped',
    FAILED: 'Failed',
    MAINTENANCE: 'Maintenance'
  }
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, te: () => true }),
  createI18n: () => ({
    install: () => undefined,
    global: { t: (k: string) => k }
  })
}))

vi.mock('@/lib/i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/i18n')>()),
  i18n: { global: { locale: { value: 'en-US' }, t: (k: string) => k } }
}))

// Stub heavy children so the test focuses on visibility logic.
vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['hierarchy', 'size', 'icon', 'disabled'],
    template: '<button :data-icon="icon" :data-h="hierarchy" :disabled="disabled"><slot /></button>'
  }
}))
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: { template: '<div data-test="tooltip"><slot /></div>' },
  TooltipTrigger: { props: ['asChild'], template: '<div><slot /></div>' },
  TooltipContent: { props: ['title'], template: '<div :data-title="title"></div>' }
}))
vi.mock('@/components/ui/skeleton/Skeleton.vue', () => ({
  default: { template: '<div data-test="skeleton"></div>' }
}))
vi.mock('@/components/badge/Badge.vue', () => ({
  default: { props: ['color'], template: '<span :data-color="color"><slot /></span>' }
}))
vi.mock('./IncreaseStorageSizeModal.vue', () => ({
  default: {
    props: ['open', 'storageId'],
    template: '<div data-test="increase-modal" :data-open="open"></div>'
  }
}))

import DesktopStorageItem from './DesktopStorageItem.vue'

const stoppedDesktop = {
  id: 'd-1',
  name: 'work-pc',
  status: 'Stopped',
  type: 'persistent',
  storage: ['s-1'],
  viewers: [],
  description: ''
} as unknown as UserDesktop

const startedDesktop = { ...stoppedDesktop, status: 'Started' } as UserDesktop

const setRole = (role: string) => {
  userRef.value = { id: 'u-1', role_id: role }
}

const setStorage = (s: Record<string, unknown> | undefined) => {
  queryData.value = s
}

describe('DesktopStorageItem', () => {
  beforeEach(() => {
    setRole('admin')
    queryIsPending.value = false
    setStorage(undefined)
  })

  it('renders skeleton while loading', () => {
    queryIsPending.value = true
    const wrapper = mount(DesktopStorageItem, {
      props: { desktop: stoppedDesktop, storageId: 's-1' }
    })
    expect(wrapper.find('[data-test="skeleton"]').exists()).toBe(true)
  })

  it('hides Increase for plain "user" role', () => {
    setRole('user')
    setStorage({ id: 's-1', status: 'ready', user_id: 'u-1', has_pending_task: false })
    const wrapper = mount(DesktopStorageItem, {
      props: { desktop: stoppedDesktop, storageId: 's-1' }
    })
    expect(wrapper.html()).not.toContain('actions.increase')
  })

  it('shows Increase for advanced/manager/admin when desktop is Stopped + storage ready', () => {
    setRole('advanced')
    setStorage({ id: 's-1', status: 'ready', user_id: 'u-1', has_pending_task: false })
    const wrapper = mount(DesktopStorageItem, {
      props: { desktop: stoppedDesktop, storageId: 's-1' }
    })
    expect(wrapper.html()).toContain('actions.increase')
    const increaseBtn = wrapper.findAll('button').find((b) => b.attributes('data-icon') === 'plus')
    expect(increaseBtn).toBeTruthy()
    expect(increaseBtn).toBeTruthy()
    expect((increaseBtn?.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('disables Increase when desktop is not Stopped', () => {
    setRole('admin')
    setStorage({ id: 's-1', status: 'ready', user_id: 'u-1', has_pending_task: false })
    const wrapper = mount(DesktopStorageItem, {
      props: { desktop: startedDesktop, storageId: 's-1' }
    })
    const increaseBtn = wrapper.findAll('button').find((b) => b.attributes('data-icon') === 'plus')
    expect(increaseBtn).toBeTruthy()
    expect((increaseBtn?.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('disables Increase when storage is not ready', () => {
    setRole('admin')
    setStorage({ id: 's-1', status: 'maintenance', user_id: 'u-1', has_pending_task: true })
    const wrapper = mount(DesktopStorageItem, {
      props: { desktop: stoppedDesktop, storageId: 's-1' }
    })
    const increaseBtn = wrapper.findAll('button').find((b) => b.attributes('data-icon') === 'plus')
    expect(increaseBtn).toBeTruthy()
    expect((increaseBtn?.element as HTMLButtonElement).disabled).toBe(true)
  })
})
