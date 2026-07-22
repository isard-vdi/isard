import type { Meta, StoryObj } from '@storybook/vue3-vite'
import SidebarToggle from './SidebarToggle.vue'

const meta: Meta<typeof SidebarToggle> = {
  component: SidebarToggle,
  title: 'Navigation/SidebarToggle',
  tags: ['autodocs'],
  argTypes: {
    open: {
      control: 'boolean',
      description: 'Whether the sidebar is open or closed'
    },
    icon: {
      control: 'text',
      description: 'Optional custom icon name'
    },
    class: {
      control: 'text',
      description: 'Additional CSS classes'
    }
  },
  render: (args) => ({
    components: { SidebarToggle },
    setup() {
      return {
        args
      }
    },
    template: `<SidebarToggle v-bind="args" />`
  })
}

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Story['args']): Story => ({ args })

export const Open = createStory({
  open: true
})

export const Close = createStory({
  open: false
})

export const OpenHover = createStory({
  open: true
})

OpenHover.parameters = {
  pseudo: { hover: true }
}

export const CloseHover = createStory({
  open: false
})

CloseHover.parameters = {
  pseudo: { hover: true }
}
