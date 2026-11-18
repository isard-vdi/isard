import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, reactive, ref } from 'vue'

const mutateMock = vi.fn()
let mutationOptions: { onSuccess: (data: unknown, variables: unknown) => void }

vi.mock('@tanstack/vue-query', () => ({
  useMutation: (options: typeof mutationOptions) => {
    mutationOptions = options
    return { mutate: mutateMock, isPending: ref(false), variables: ref(undefined) }
  }
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  extendDesktopTimeoutMutation: () => ({})
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      `${key.split('.').pop()}:${params?.name ?? params?.count ?? params?.minutes ?? ''}`,
    te: () => false,
    d: (value: string) => value
  })
}))

const sessionStore = reactive({ modalOpen: false })
vi.mock('@/stores/session', () => ({ useSessionStore: () => sessionStore }))

vi.mock('@/components/ui/toast', () => ({ toast: { error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ describeApiError: () => 'error' }))
vi.mock('@/lib/utils', () => ({ cn: (...classes: string[]) => classes.join(' ') }))
vi.mock('@/components/ui/spinner', () => ({ Spinner: { template: '<i />' } }))

vi.mock('@/components/modal', () => ({
  AlertModal: {
    props: ['open', 'level', 'size', 'description'],
    emits: ['update:open'],
    template: `<div data-test="modal" :data-open="open" :data-level="level">
      <p data-test="description">{{ description }}</p>
      <slot name="description" />
      <footer><slot name="footer" /></footer>
      <button data-test="close" @click="$emit('update:open', false)" />
    </div>`
  }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['disabled'],
    emits: ['click'],
    template:
      '<button data-test="extend" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))

import {
  addDesktopTimeout,
  clearDesktopTimeouts,
  desktopTimeouts,
  type DesktopTimeoutWarning
} from '@/lib/desktop-timeout'
import DesktopTimeoutModal from './DesktopTimeoutModal.vue'

const warning = (id: string, overrides: Partial<DesktopTimeoutWarning> = {}) => ({
  key: id,
  desktopId: id,
  name: `Desktop ${id}`,
  stopsAt: '2026-11-18T10:00+0000',
  level: 'warning' as const,
  extendMinutes: null,
  ...overrides
})

describe('DesktopTimeoutModal', () => {
  beforeEach(() => {
    mutateMock.mockReset()
    clearDesktopTimeouts()
    sessionStore.modalOpen = false
  })

  const modal = (wrapper: ReturnType<typeof mount>) => wrapper.find('[data-test="modal"]')

  it('stays closed without warnings', () => {
    const wrapper = mount(DesktopTimeoutModal)
    expect(modal(wrapper).attributes('data-open')).toBe('false')
  })

  it('shows a single warning as the modal description with its extend action', async () => {
    addDesktopTimeout(warning('d1', { extendMinutes: 30 }))
    const wrapper = mount(DesktopTimeoutModal)

    expect(modal(wrapper).attributes('data-open')).toBe('true')
    expect(wrapper.find('[data-test="description"]').text()).toBe('description:Desktop d1')
    expect(wrapper.findAll('li')).toHaveLength(0)

    await wrapper.find('footer [data-test="extend"]').trigger('click')
    expect(mutateMock).toHaveBeenCalledWith({ path: { desktop_id: 'd1' } })
  })

  it('lists every warning, soonest first, under the most severe level', () => {
    addDesktopTimeout(warning('late', { stopsAt: '2026-11-18T11:00+0000', level: 'info' }))
    addDesktopTimeout(warning('soon', { stopsAt: '2026-11-18T10:05+0000', level: 'danger' }))
    const wrapper = mount(DesktopTimeoutModal)

    expect(wrapper.find('[data-test="description"]').text()).toBe('description-multiple:2')
    expect(wrapper.findAll('li').map((li) => li.find('span:last-of-type').text())).toEqual([
      'description:Desktop soon',
      'description:Desktop late'
    ])
    expect(modal(wrapper).attributes('data-level')).toBe('danger')
  })

  it('extends the desktop of the row and keeps the other warnings', async () => {
    addDesktopTimeout(warning('d1', { extendMinutes: 30 }))
    addDesktopTimeout(warning('d2'))
    const wrapper = mount(DesktopTimeoutModal)

    const buttons = wrapper.findAll('li [data-test="extend"]')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(mutateMock).toHaveBeenCalledWith({ path: { desktop_id: 'd1' } })

    mutationOptions.onSuccess(undefined, { path: { desktop_id: 'd1' } })
    expect(desktopTimeouts.value.map((w) => w.key)).toEqual(['d2'])
  })

  it('waits for the session modal to close and keeps the warnings meanwhile', async () => {
    sessionStore.modalOpen = true
    addDesktopTimeout(warning('d1'))
    const wrapper = mount(DesktopTimeoutModal)

    expect(modal(wrapper).attributes('data-open')).toBe('false')

    sessionStore.modalOpen = false
    await nextTick()

    expect(modal(wrapper).attributes('data-open')).toBe('true')
    expect(desktopTimeouts.value).toHaveLength(1)
  })

  it('discards every warning when the modal is dismissed', async () => {
    addDesktopTimeout(warning('d1'))
    addDesktopTimeout(warning('d2'))
    const wrapper = mount(DesktopTimeoutModal)

    await wrapper.find('[data-test="close"]').trigger('click')

    expect(desktopTimeouts.value).toEqual([])
  })
})
