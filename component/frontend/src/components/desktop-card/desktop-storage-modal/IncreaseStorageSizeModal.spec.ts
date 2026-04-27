import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mutateMock = vi.fn()
const isPending = ref(false)

vi.mock('@tanstack/vue-query', () => ({
  useMutation: (opts: {
    mutationFn?: unknown
    onSuccess?: () => void
    onError?: (e: unknown) => void
  }) => ({
    mutate: (vars: unknown) => mutateMock(vars, opts),
    isPending
  }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  increaseStorageSizeApiV4ItemStorageStorageIdPriorityPriorityIncreaseIncrementPutMutation:
    () => ({}),
  getStorageApiV4ItemStorageStorageIdGetQueryKey: () => [{}],
  getStorageTaskApiV4ItemStorageStorageIdTaskGetQueryKey: () => [{}]
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

vi.mock('@/components/modal', () => ({
  Modal: {
    name: 'Modal',
    props: ['open', 'size', 'title', 'description', 'closeOnBackdropClick'],
    emits: ['close'],
    template: '<div data-test="modal" :data-open="open"><slot /><slot name="footer" /></div>'
  }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['hierarchy', 'disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))

vi.mock('@/components/icon', () => ({
  Icon: { template: '<i></i>' }
}))

vi.mock('@/components/input-field/InputField.vue', () => ({
  default: {
    name: 'InputField',
    props: ['modelValue', 'type', 'min', 'step', 'destructive', 'disabled', 'placeholder', 'id'],
    emits: ['update:modelValue'],
    template:
      '<input :data-test="id" :value="modelValue" :type="type" @input="$emit(\'update:modelValue\', Number($event.target.value))" />'
  }
}))

import IncreaseStorageSizeModal from './IncreaseStorageSizeModal.vue'

describe('IncreaseStorageSizeModal', () => {
  beforeEach(() => {
    mutateMock.mockReset()
    isPending.value = false
  })

  it('submits the integer increment with low priority', async () => {
    const wrapper = mount(IncreaseStorageSizeModal, {
      props: { open: true, storageId: 's-9' }
    })
    const input = wrapper.find('input[data-test="storage-increment"]')
    await input.setValue('25')

    // The footer's last button is the Increase confirm.
    const buttons = wrapper.findAll('button')
    await buttons[buttons.length - 1].trigger('click')

    expect(mutateMock).toHaveBeenCalledTimes(1)
    const [vars] = mutateMock.mock.calls[0]
    expect(vars).toEqual({
      path: { storage_id: 's-9', priority: 'low', increment: 25 }
    })
  })

  it('disables the confirm button when the field is empty or zero', async () => {
    const wrapper = mount(IncreaseStorageSizeModal, {
      props: { open: true, storageId: 's-9' }
    })
    const input = wrapper.find('input[data-test="storage-increment"]')
    await input.setValue('0')

    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons[buttons.length - 1]
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(true)

    await input.setValue('-3')
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refuses fractional input on form submit', async () => {
    const wrapper = mount(IncreaseStorageSizeModal, {
      props: { open: true, storageId: 's-9' }
    })
    const input = wrapper.find('input[data-test="storage-increment"]')
    await input.setValue('5.7')

    // Both the button click and the form submit go through the same
    // ``isInvalid()`` gate, so non-integer increments are rejected
    // rather than silently floored.
    const form = wrapper.find('form')
    await form.trigger('submit')
    expect(mutateMock).not.toHaveBeenCalled()
  })
})
