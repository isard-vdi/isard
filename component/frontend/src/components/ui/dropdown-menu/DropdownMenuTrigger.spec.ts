/* eslint-disable vue/one-component-per-file */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent } from '.'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const components = {
  TooltipProvider,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  Button
}

const MENU = `<DropdownMenuContent><div data-testid="menu">menu</div></DropdownMenuContent>`

const WITHOUT_TOOLTIP = defineComponent({
  components,
  template: `
    <TooltipProvider>
      <DropdownMenu>
        <DropdownMenuTrigger><Button icon="dots-vertical" /></DropdownMenuTrigger>
        ${MENU}
      </DropdownMenu>
    </TooltipProvider>`
})

// A Tooltip between DropdownMenu and DropdownMenuTrigger makes MenuAnchor register on the
// tooltip's PopperRoot, leaving the menu unanchored — so the tooltip must wrap the whole menu.
const TOOLTIP_WRAPPING_MENU = defineComponent({
  components,
  template: `
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="inline-flex">
            <DropdownMenu>
              <DropdownMenuTrigger><Button icon="dots-vertical" /></DropdownMenuTrigger>
              ${MENU}
            </DropdownMenu>
          </span>
        </TooltipTrigger>
        <TooltipContent title="more" />
      </Tooltip>
    </TooltipProvider>`
})

async function openMenu(comp: unknown) {
  const wrapper = mount(comp as never, { attachTo: document.body })
  const trigger = wrapper.find('[aria-haspopup="menu"]')
  expect(trigger.exists()).toBe(true)
  await trigger.trigger('click', { button: 0, ctrlKey: false })
  await new Promise((r) => setTimeout(r, 50))
  const result = {
    content: document.body.querySelector('[data-testid="menu"]'),
    popperStyle: document.body
      .querySelector('[data-reka-popper-content-wrapper]')
      ?.getAttribute('style')
  }
  wrapper.unmount()
  return result
}

describe('DropdownMenuTrigger combined with a Tooltip', () => {
  it('anchors the menu to its trigger without a tooltip', async () => {
    const { content, popperStyle } = await openMenu(WITHOUT_TOOLTIP)
    expect(content).not.toBeNull()
    expect(popperStyle).toContain('--reka-popper-anchor-width')
  })

  it('still anchors the menu when a tooltip wraps the whole dropdown', async () => {
    const { content, popperStyle } = await openMenu(TOOLTIP_WRAPPING_MENU)
    expect(content).not.toBeNull()
    expect(popperStyle).toContain('--reka-popper-anchor-width')
  })
})
