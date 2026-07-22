import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Icon } from '@/components/icon'

const meta = {
  component: Icon,
  title: 'Icon/Icon',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=3463-407484'
    }
  },
  argTypes: {
    name: {
      control: 'text'
    },
    alt: {
      control: 'text'
    },
    strokeColor: {
      control: 'text'
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl', 'xxl']
    },
    fillColor: {
      control: 'text'
    }
  },
  render: (args) => ({
    components: { Icon },
    setup() {
      return {
        args
      }
    },
    template: `<Icon :name="args.name" :alt="args.alt" :strokeColor="args.strokeColor" :fillColor="args.fillColor" :size="args.size" />`
  })
} satisfies Meta<typeof Icon>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const FaceSmile = createStory({ name: 'face-smile' })
