import { describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

import Icon from './Icon.vue'

// Resolving an icon pulls its module through vite-node, so waiting on the
// microtask queue alone is not enough — poll until the svg lands.
async function settle(wrapper: VueWrapper) {
  await vi.waitFor(() => {
    expect(wrapper.find('svg').exists()).toBe(true)
  })
}

async function mountIcon(name: string) {
  const wrapper = mount(Icon, { props: { name } })
  await settle(wrapper)
  return wrapper
}

describe('Icon', () => {
  it('resolves a name to its inlined svg', async () => {
    const wrapper = await mountIcon('play')
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('swaps the svg when the name changes', async () => {
    const wrapper = await mountIcon('trash-01')
    const before = wrapper.find('svg').html()

    await wrapper.setProps({ name: 'copy-01' })
    await vi.waitFor(() => {
      expect(wrapper.find('svg').html()).not.toBe(before)
    })
  })

  it('falls back to face-smile for an unknown name', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await mountIcon('not-a-real-icon')

    expect(error).toHaveBeenCalledWith(expect.stringContaining('no such icon'))
    expect(wrapper.find('svg').exists()).toBe(true)
    error.mockRestore()
  })
})
