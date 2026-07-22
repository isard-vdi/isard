import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { BadgeInfo } from '.'

const meta = {
  component: BadgeInfo,
  title: 'Badge/BadgeInfo',
  tags: ['autodocs'],
  argTypes: {
    icon: {
      control: 'text'
    },
    content: {
      control: 'text'
    }
  },
  render: (args) => ({
    components: { BadgeInfo },
    setup() {
      return {
        args
      }
    },
    template: `<BadgeInfo v-bind="args" />`
  })
} satisfies Meta<typeof BadgeInfo>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Story['args']): Story => ({ args })

export const Default = createStory({
  icon: 'power-01',
  content: '3'
})
