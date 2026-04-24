import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'

import { DesktopCardSkeleton } from '@/components/desktop-card'

const meta = {
  component: DesktopCardSkeleton,
  title: 'Desktop Card/DesktopCardSkeleton',
  tags: ['autodocs', 'DesktopCard'],
  parameters: {
    design: {
      type: 'figma',
      url: ''
    }
  },
  argTypes: {
    variant: {
      control: 'select',
      options: ['stopped', 'started']
    }
  },
  render: (args) => ({
    components: {
      DesktopCardSkeleton
    },
    setup() {
      return {
        args
      }
    },
    template: `
      <DesktopCardSkeleton :variant="args.variant" class="w-[426px] h-[310px]" />
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DesktopCardSkeleton>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: args,
  parameters: { ...parameters }
})

export const Stopped = createStory({
  variant: 'stopped'
})
export const Started = createStory({
  variant: 'started'
})
