import type { Meta, StoryObj } from '@storybook/vue3'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'

const meta = {
  component: Input,
  title: 'Input',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=3531-403089'
    }
  },
  render: (args) => ({
    components: { Input, Label },
    setup() {
      return {
        args
      }
    },
    template: `<Icon :name="args.name"/>`
  })
} satisfies Meta<typeof Input>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const FaceSmile = createStory({ name: 'face-smile' })
