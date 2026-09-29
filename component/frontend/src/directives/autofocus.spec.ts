import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref, withDirectives } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { vAutofocus } from './autofocus'

const frame = async () => {
  await nextTick()
  vi.runAllTimers()
}

let wrapper: VueWrapper | undefined

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame'] })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
})

const mountWith = (render: () => ReturnType<typeof h>) => {
  wrapper = mount(defineComponent({ render }), { attachTo: document.body })
  return wrapper
}

describe('vAutofocus', () => {
  it('focuses the element itself', async () => {
    mountWith(() => withDirectives(h('input', { id: 'a' }), [[vAutofocus]]))
    await frame()
    expect(document.activeElement?.id).toBe('a')
  })

  it('focuses the first field inside a wrapper', async () => {
    mountWith(() =>
      withDirectives(
        h('div', [h('input', { type: 'hidden' }), h('textarea', { id: 't' }), h('input')]),
        [[vAutofocus]]
      )
    )
    await frame()
    expect(document.activeElement?.id).toBe('t')
  })

  it('focuses a button', async () => {
    mountWith(() => withDirectives(h('button', { id: 'b' }), [[vAutofocus]]))
    await frame()
    expect(document.activeElement?.id).toBe('b')
  })

  it('opts out with false', async () => {
    mountWith(() => withDirectives(h('input', { id: 'a' }), [[vAutofocus, false]]))
    await frame()
    expect(document.activeElement).toBe(document.body)
  })

  it('waits for a disabled field to be enabled', async () => {
    const disabled = ref(true)
    mountWith(() =>
      withDirectives(h('input', { id: 'a', disabled: disabled.value }), [[vAutofocus]])
    )
    await frame()
    expect(document.activeElement).toBe(document.body)
    disabled.value = false
    await frame()
    expect(document.activeElement?.id).toBe('a')
  })

  it('does not steal focus the user moved meanwhile', async () => {
    const disabled = ref(true)
    mountWith(() =>
      h('div', [
        h('button', { id: 'other' }),
        withDirectives(h('input', { id: 'a', disabled: disabled.value }), [[vAutofocus]])
      ])
    )
    await frame()
    ;(document.getElementById('other') as HTMLButtonElement).focus()
    disabled.value = false
    await frame()
    expect(document.activeElement?.id).toBe('other')
  })
})
