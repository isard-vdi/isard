import type { Meta, StoryObj } from '@storybook/vue3'
import { Switch } from '@/components/ui/switch'

const meta = {
  component: Switch,
  title: 'Switch',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  }
} satisfies Meta<typeof Switch>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
