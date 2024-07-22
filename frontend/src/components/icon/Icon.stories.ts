import type { Meta, StoryObj } from '@storybook/vue3'
import { Icon } from '@/components/icon'

const meta = {
  component: Icon,
  title: 'Icon',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=3463-407484'
    }
  },
  render: (args) => ({
    components: { Icon },
    setup() {
      return {
        args
      }
    },
    template: `<Icon :name="args.name"/>`
  })
} satisfies Meta<typeof Icon>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const FaceSmile = createStory({ name: 'face-smile' })
