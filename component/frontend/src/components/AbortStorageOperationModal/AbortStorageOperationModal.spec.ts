import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mutateMock = vi.fn()
const isPending = ref(false)
const isError = ref(false)
const invalidateQueriesMock = vi.fn()
const toastSuccessMock = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useMutation: (opts: { onSuccess?: () => void }) => ({
    mutate: (vars: unknown) => mutateMock(vars, opts),
    isPending,
    isError
  }),
  useQueryClient: () => ({ invalidateQueries: invalidateQueriesMock })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  abortStorageOperationsMutation: () => ({}),
  getStorageQueryKey: (o: { path: { storage_id: string } }) => [{ _id: 'getStorage', ...o.path }],
  getStorageTaskQueryKey: (o: { path: { storage_id: string } }) => [
    { _id: 'getStorageTask', ...o.path }
  ]
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

vi.mock('@/components/ui/toast', () => ({
  toast: { success: (...args: unknown[]) => toastSuccessMock(...args) }
}))

vi.mock('@/components/modal', () => ({
  AlertModal: {
    name: 'AlertModal',
    props: ['open', 'level', 'size', 'title', 'description'],
    emits: ['close'],
    template:
      '<div data-test="alert-modal" :data-open="open"><slot name="description" /><slot /><slot name="footer" /></div>'
  }
}))

vi.mock('@/components/ui/alert', () => ({
  Alert: { template: '<div data-test="alert"><slot /></div>' },
  AlertTitle: { template: '<div><slot /></div>' },
  AlertDescription: { template: '<div><slot /></div>' }
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

import AbortStorageOperationModal from './AbortStorageOperationModal.vue'

const mountModal = () =>
  mount(AbortStorageOperationModal, {
    props: { open: true, storageId: 's-1', desktopName: 'work-pc' }
  })

const confirm = async (wrapper: ReturnType<typeof mountModal>) => {
  const buttons = wrapper.findAll('button')
  await buttons[buttons.length - 1].trigger('click')
  return mutateMock.mock.calls[0][1] as { onSuccess?: () => void }
}

describe('AbortStorageOperationModal', () => {
  beforeEach(() => {
    mutateMock.mockReset()
    invalidateQueriesMock.mockReset()
    toastSuccessMock.mockReset()
    isPending.value = false
    isError.value = false
  })

  it('calls the abort mutation with the storage id', async () => {
    const wrapper = mountModal()
    await confirm(wrapper)

    expect(mutateMock).toHaveBeenCalledTimes(1)
    expect(mutateMock.mock.calls[0][0]).toEqual({ path: { storage_id: 's-1' } })
  })

  it('invalidates, notifies and closes on success while the mutation is still pending', async () => {
    const wrapper = mountModal()
    const opts = await confirm(wrapper)

    // query-core settles the mutation only after onSuccess returns.
    isPending.value = true
    opts.onSuccess?.()

    expect(invalidateQueriesMock).toHaveBeenCalledTimes(2)
    expect(toastSuccessMock).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toEqual([[]])
  })

  it('ignores a dismiss while the mutation is pending', () => {
    isPending.value = true
    const wrapper = mountModal()
    wrapper.findComponent({ name: 'AlertModal' }).vm.$emit('close')

    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('shows the error alert when the mutation fails', async () => {
    isError.value = true
    const wrapper = mountModal()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-test="alert"]').exists()).toBe(true)
  })
})
