import type { Meta, StoryObj } from '@storybook/vue3'
import { Label } from '@/components/ui/label'

const meta = {
  component: Label,
  title: 'Label',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=3531-403089'
    }
  },
  render: (args) => ({
    components: { Label },
    setup() {
      return {
        args
      }
    },
    template: `<Label>Nom</Label>`
  })
} satisfies Meta<typeof Label>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
