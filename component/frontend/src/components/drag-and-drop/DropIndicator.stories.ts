import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { DropIndicator } from '.'

const meta = {
  component: DropIndicator,
  title: 'DragAndDrop/DropIndicator',
  tags: ['autodocs'],
  argTypes: {
    edge: {
      control: { type: 'select' },
      options: ['top', 'bottom', 'left', 'right']
    },
    gap: { control: 'text' }
  },
  render: (args) => ({
    components: { DropIndicator },
    setup() {
      return {
        args
      }
    },
    template: `
    <div style="position: relative; width: 200px; height: 200px; border: 1px solid #ccc; margin-top: 20px;"></div>
    <DropIndicator :edge="args.edge" :gap="args.gap" />
    <div></div>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DropIndicator>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

export const TopEdge = createStory({
  edge: 'top',
  gap: '8px'
})

export const BottomEdge = createStory({
  edge: 'bottom',
  gap: '8px'
})

export const LeftEdge = createStory({
  edge: 'left',
  gap: '8px'
})

export const RightEdge = createStory({
  edge: 'right',
  gap: '8px'
})
