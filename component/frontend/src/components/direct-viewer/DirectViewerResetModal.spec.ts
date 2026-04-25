import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mutateMock = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useMutation: () => ({ mutate: mutateMock, isPending: ref(false) })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  resetDesktopApiV4ItemDesktopTokenTokenResetDesktopPutMutation: () => ({})
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: {
    name: 'Dialog',
    props: ['open'],
    emits: ['update:open'],
    template: '<div data-test="dialog" :data-open="open"><slot /></div>'
  },
  DialogContent: { template: '<div><slot /></div>' },
  DialogDescription: { template: '<div><slot /></div>' },
  DialogHeader: { template: '<div><slot /></div>' },
  DialogTitle: { template: '<div><slot /></div>' }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))

import DirectViewerResetModal from './DirectViewerResetModal.vue'

describe('DirectViewerResetModal', () => {
  beforeEach(() => {
    mutateMock.mockReset()
  })

  it('forwards the open prop to the underlying Dialog', () => {
    const wrapper = mount(DirectViewerResetModal, { props: { open: true, token: 't' } })
    expect(wrapper.find('[data-test="dialog"]').attributes('data-open')).toBe('true')
  })

  it('calls reset mutation with token and emits close on settled', async () => {
    const wrapper = mount(DirectViewerResetModal, { props: { open: true, token: 'tok-1' } })
    await wrapper.find('button').trigger('click')

    expect(mutateMock).toHaveBeenCalledTimes(1)
    const [args, opts] = mutateMock.mock.calls[0]
    expect(args).toEqual({ path: { token: 'tok-1' } })

    expect(typeof opts.onSettled).toBe('function')
    opts.onSettled()
    expect(wrapper.emitted('close')).toEqual([[]])
  })

  it('emits close when the dialog requests closure with open=false', async () => {
    const wrapper = mount(DirectViewerResetModal, { props: { open: true, token: 'tok' } })
    const dialog = wrapper.findComponent({ name: 'Dialog' })
    expect(dialog.exists()).toBe(true)
    dialog.vm.$emit('update:open', false)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('close')).toEqual([[]])
  })

  it('does not emit close when the dialog reports open=true', async () => {
    const wrapper = mount(DirectViewerResetModal, { props: { open: true, token: 'tok' } })
    const dialog = wrapper.findComponent({ name: 'Dialog' })
    dialog.vm.$emit('update:open', true)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
