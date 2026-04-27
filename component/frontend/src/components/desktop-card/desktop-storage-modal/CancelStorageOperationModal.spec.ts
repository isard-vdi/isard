import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mutateMock = vi.fn()
const isPending = ref(false)
const invalidateQueriesMock = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useMutation: (opts: {
    mutationFn?: unknown
    onSuccess?: () => void
    onError?: (e: unknown) => void
  }) => ({
    mutate: (vars: unknown) => mutateMock(vars, opts),
    isPending
  }),
  useQueryClient: () => ({ invalidateQueries: invalidateQueriesMock })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  abortStorageOperationsApiV4ItemStorageStorageIdAbortOperationsPutMutation: () => ({}),
  getStorageApiV4ItemStorageStorageIdGetQueryKey: (o: { path: { storage_id: string } }) => [
    { _id: 'getStorage', ...o.path }
  ],
  getStorageTaskApiV4ItemStorageStorageIdTaskGetQueryKey: (o: { path: { storage_id: string } }) => [
    { _id: 'getStorageTask', ...o.path }
  ]
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

vi.mock('@/components/modal', () => ({
  AlertModal: {
    name: 'AlertModal',
    props: ['open', 'level', 'size', 'loading', 'title', 'description'],
    emits: ['close'],
    template:
      '<div data-test="alert-modal" :data-open="open" :data-loading="loading"><div data-test="title">{{ title }}</div><slot /><slot name="footer" /></div>'
  }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['hierarchy', 'disabled'],
    emits: ['click'],
    template:
      '<button :data-h="hierarchy" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))

vi.mock('@/components/icon', () => ({
  Icon: { template: '<i></i>' }
}))

import CancelStorageOperationModal from './CancelStorageOperationModal.vue'

describe('CancelStorageOperationModal', () => {
  beforeEach(() => {
    mutateMock.mockReset()
    invalidateQueriesMock.mockReset()
    isPending.value = false
  })

  it('forwards open to AlertModal', () => {
    const wrapper = mount(CancelStorageOperationModal, {
      props: { open: true, storageId: 's-1' }
    })
    expect(wrapper.find('[data-test="alert-modal"]').attributes('data-open')).toBe('true')
  })

  it('calls abort mutation with storage_id when confirmed', async () => {
    const wrapper = mount(CancelStorageOperationModal, {
      props: { open: true, storageId: 's-42', desktopName: 'work-pc' }
    })
    // Footer slot has [Dismiss, Confirm] — second button is the confirm.
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    await buttons[buttons.length - 1].trigger('click')

    expect(mutateMock).toHaveBeenCalledTimes(1)
    const [vars] = mutateMock.mock.calls[0]
    expect(vars).toEqual({ path: { storage_id: 's-42' } })
  })

  it('invalidates storage + task queries on success and emits close', () => {
    const wrapper = mount(CancelStorageOperationModal, {
      props: { open: true, storageId: 's-1' }
    })
    const buttons = wrapper.findAll('button')
    buttons[buttons.length - 1].trigger('click')

    const [, opts] = mutateMock.mock.calls[0]
    opts.onSuccess()

    expect(invalidateQueriesMock).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('close')).toEqual([[]])
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('emits error and close when the mutation fails', () => {
    const wrapper = mount(CancelStorageOperationModal, {
      props: { open: true, storageId: 's-1' }
    })
    wrapper.findAll('button')[1].trigger('click')
    const [, opts] = mutateMock.mock.calls[0]
    opts.onError({ description: 'nope' })

    const events = wrapper.emitted('error')
    expect(events).toBeTruthy()
    expect(events?.[0]?.[0]).toBe('nope')
    expect(wrapper.emitted('close')).toEqual([[]])
  })

  it('ignores close while the mutation is pending', () => {
    isPending.value = true
    const wrapper = mount(CancelStorageOperationModal, {
      props: { open: true, storageId: 's-1' }
    })
    wrapper.findComponent({ name: 'AlertModal' }).vm.$emit('close')
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
