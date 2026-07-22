import type { Meta, StoryObj } from '@storybook/vue3-vite'
import Separator from './Separator.vue'

const meta: Meta<typeof Separator> = {
  title: 'UI/Separator',
  component: Separator,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  argTypes: {
    orientation: {
      control: { type: 'select' },
      options: ['horizontal', 'vertical']
    },
    decorative: {
      control: { type: 'boolean' }
    },
    color: {
      control: { type: 'color' }
    }
  }
}

export default meta
type Story = StoryObj<typeof meta>

export const Horizontal: Story = {
  args: {
    orientation: 'horizontal'
  },
  render: (args) => ({
    components: { Separator },
    setup() {
      return { args }
    },
    template: `
            <div class="w-64 space-y-4">
                <div>
                    <h4 class="text-sm font-medium leading-none">Section Title</h4>
                    <p class="text-sm text-muted-foreground">
                        Content above the separator.
                    </p>
                </div>
                <Separator v-bind="args" />
                <div>
                    <h4 class="text-sm font-medium leading-none">Another Section</h4>
                    <p class="text-sm text-muted-foreground">
                        Content below the separator.
                    </p>
                </div>
            </div>
        `
  })
}

export const HorizontalWithText: Story = {
  args: {
    orientation: 'horizontal',
    label: 'Section Divider'
  },
  render: (args) => ({
    components: { Separator },
    setup() {
      return { args }
    },
    template: `
            <div class="w-64 space-y-4">
                <div>
                    <h4 class="text-sm font-medium leading-none">Section Title</h4>
                    <p class="text-sm text-muted-foreground">
                        Content above the separator.
                    </p>
                </div>
                <Separator v-bind="args" />
                <div>
                    <h4 class="text-sm font-medium leading-none">Another Section</h4>
                    <p class="text-sm text-muted-foreground">
                        Content below the separator.
                    </p>
                </div>
            </div>
        `
  })
}

export const Vertical: Story = {
  args: {
    orientation: 'vertical'
  },
  render: (args) => ({
    components: { Separator },
    setup() {
      return { args }
    },
    template: `
            <div class="flex h-20 items-center space-x-4 text-sm">
                <div>Blog</div>
                <Separator v-bind="args" />
                <div>Docs</div>
                <Separator v-bind="args" />
                <div>Source</div>
            </div>
        `
  })
}
