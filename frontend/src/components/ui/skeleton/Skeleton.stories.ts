import type { Meta, StoryObj } from '@storybook/vue3'
import { Skeleton } from '.'

const meta = {
  component: Skeleton,
  title: 'Skeleton',
  tags: ['autodocs']
} satisfies Meta<typeof Skeleton>

export default meta
type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  class: 'h-6'
})
