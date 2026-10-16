import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/components/icon', () => ({
  Icon: { name: 'Icon', props: ['name'], template: '<i :data-icon="name" />' }
}))

import VisibilityToggle from './VisibilityToggle.vue'

type ToggleProps = InstanceType<typeof VisibilityToggle>['$props']

const mountToggle = (props: Partial<ToggleProps> & { modelValue: ToggleProps['modelValue'] }) =>
  mount(VisibilityToggle, { props: { label: 'toggle', ...props } })

const iconOf = (wrapper: ReturnType<typeof mountToggle>) =>
  wrapper.find('[data-icon]').attributes('data-icon')

describe('VisibilityToggle', () => {
  it('shows an open eye when everything is visible', () => {
    expect(iconOf(mountToggle({ modelValue: true }))).toBe('eye')
  })

  it('shows a crossed eye when nothing is visible', () => {
    // force-mount keeps the indicator rendered while unchecked; without it
    // reka-ui hides it and the cell would look empty.
    expect(iconOf(mountToggle({ modelValue: false }))).toBe('eye-off')
  })

  it('shows a dash for a mixed aggregate', () => {
    expect(iconOf(mountToggle({ modelValue: 'indeterminate' }))).toBe('minus')
  })

  it('turns a mixed aggregate fully visible, never fully hidden', async () => {
    // The whole reason this is built on CheckboxRoot rather than ui/checkbox,
    // which cycles false -> true -> indeterminate and lets a user *set* mixed.
    const wrapper = mountToggle({ modelValue: 'indeterminate' })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('emits a plain boolean, not the tri-state', async () => {
    const wrapper = mountToggle({ modelValue: false })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('stays silent while disabled', async () => {
    const wrapper = mountToggle({ modelValue: false, disabled: true })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('exposes the label to assistive tech', () => {
    const wrapper = mountToggle({ modelValue: false, label: 'Show Ubuntu for everyone' })
    expect(wrapper.find('button').attributes('aria-label')).toBe('Show Ubuntu for everyone')
  })
})
