import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { Button } from '.'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const mountInTooltip = (template: string) =>
  mount(
    defineComponent({
      components: { UiButton: Button, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger },
      template: `<TooltipProvider><Tooltip>${template}</Tooltip></TooltipProvider>`
    }),
    { attachTo: document.body }
  )

describe('Button accessible name', () => {
  it('uses the tooltip title for an icon-only button in a tooltip trigger', async () => {
    const wrapper = mountInTooltip(`
      <TooltipTrigger as-child><UiButton icon="trash-04" /></TooltipTrigger>
      <TooltipContent title="Delete" />
    `)
    await nextTick()
    expect(wrapper.get('button').attributes('aria-label')).toBe('Delete')
    wrapper.unmount()
  })

  it('keeps an explicit aria-label', async () => {
    const wrapper = mountInTooltip(`
      <TooltipTrigger as-child><UiButton icon="trash-04" aria-label="Remove item" /></TooltipTrigger>
      <TooltipContent title="Delete" />
    `)
    await nextTick()
    expect(wrapper.get('button').attributes('aria-label')).toBe('Remove item')
    wrapper.unmount()
  })

  it('uses the tooltip title when aria-label is passed as undefined', async () => {
    const wrapper = mountInTooltip(`
      <TooltipTrigger as-child><UiButton icon="trash-04" :aria-label="undefined" /></TooltipTrigger>
      <TooltipContent title="Delete" />
    `)
    await nextTick()
    expect(wrapper.get('button').attributes('aria-label')).toBe('Delete')
    wrapper.unmount()
  })

  it('does not override the visible text of a labelled button', async () => {
    const wrapper = mountInTooltip(`
      <TooltipTrigger as-child><UiButton icon="stop">Stop all</UiButton></TooltipTrigger>
      <TooltipContent title="Stops every running desktop" />
    `)
    await nextTick()
    expect(wrapper.get('button').attributes('aria-label')).toBeUndefined()
    wrapper.unmount()
  })

  it('does not take the title outside the trigger', async () => {
    const wrapper = mountInTooltip(`
      <TooltipTrigger as-child><span>trigger</span></TooltipTrigger>
      <TooltipContent title="Delete" />
      <UiButton icon="trash-04" />
    `)
    await nextTick()
    expect(wrapper.get('button').attributes('aria-label')).toBeUndefined()
    wrapper.unmount()
  })

  it('has no aria-label outside a tooltip', () => {
    const wrapper = mount(Button, { props: { icon: 'trash-04' } })
    expect(wrapper.get('button').attributes('aria-label')).toBeUndefined()
  })
})
