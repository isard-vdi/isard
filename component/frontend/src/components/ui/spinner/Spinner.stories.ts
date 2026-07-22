import { type Meta, type StoryObj } from '@storybook/vue3-vite'
import { Spinner } from '@/components/ui/spinner'

const meta: Meta<typeof Spinner> = {
  component: Spinner,
  title: 'UI/Spinner',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=9164-101878&t=fBKhQthh6gBlLlbp-4'
    }
  },
  argTypes: {
    size: {
      control: 'select',
      options: ['sm', 'md'],
      value: 'md',
      type: 'string',
      description: 'Size of the spinner'
    },
    color: {
      control: 'select',
      options: ['green', 'red'],
      type: 'string',
      description: 'Color of the spinner'
    },
    class: {
      control: 'text',
      description: 'Additional CSS classes to apply to the spinner'
    }
  },
  render: (args) => ({
    components: { Spinner },
    setup() {
      return { args }
    },
    template: `<Spinner :size="args.size" :color="args.color" :class="args.class" />`
  })
}

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {}
} satisfies Story

export const Red: Story = {
  args: { color: 'red' }
} satisfies Story

export const Small: Story = {
  args: { size: 'sm' }
} satisfies Story

export const SmallRed: Story = {
  args: { size: 'sm', color: 'red' }
} satisfies Story

export const WithTitle: Story = {
  args: {},
  render: (args) => ({
    components: { Spinner },
    setup() {
      return { args }
    },
    template: `
      <div class="flex flex-col items-center gap-6">
        <Spinner v-bind="args" />
        <div class="flex flex-col items-center gap-4">
          <h2 class="text-display-sm font-bold text-gray-warm-800">Creating Desktop</h2>
          <p class="text-base text-center text-gray-warm-600 max-w-140">
            We are carefully placing each piece in its place,<br />
            don't worry, we won't take long
          </p>
        </div>
      </div>
    `
  })
} satisfies Story

export const WithLabel: Story = {
  args: { size: 'sm' },
  render: (args) => ({
    components: { Spinner },
    setup() {
      return { args }
    },
    template: `
      <div class="inline-flex items-center gap-3">
        <Spinner v-bind="args" />
        <div class="text-xs font-medium text-black">Starting desktop...</div>
      </div>
    `
  })
} satisfies Story
