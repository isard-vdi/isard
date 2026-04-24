import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { MetricItem } from '.'

const meta = {
  component: MetricItem,
  title: 'MetricItem',
  tags: ['autodocs'],
  render: (args) => ({
    components: { MetricItem },
    setup() {
      return {
        args
      }
    },
    template: `<MetricItem v-bind="args" />`
  })
} satisfies Meta<typeof MetricItem>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Story['args']): Story => ({
  args
})

export const SorageUsed = createStory({
  title: 'Memory used (GB)',
  total: 32,
  current: 14
})

export const CreatedTemplates = createStory({
  title: 'Created templates',
  total: 10,
  current: 6
})

export const StartedDesktops = createStory({
  title: 'Started desktops',
  total: 6,
  current: 6
})

export const NoLimit = createStory({
  title: 'Started desktops',
  current: 6
})
