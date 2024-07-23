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
  argTypes: {
    label: { control: 'text' },
    placeholder: { control: 'text' },
    size: { control: 'select', options: ['sm', 'md'] },
    destructive: { control: 'boolean' },
    hint: { control: 'text' }
  },
  render: (args) => ({
    components: { Input, Label },
    setup() {
      return {
        args
      }
    },
    // TODO: Add the help and type prop to the Input component
    template: `
      <Label v-if="args.label" for="input">{{ args.label }}</Label>
      <Input id="input" :placeholder="args.placeholder" :size="args.size" :destructive="args.destructive" :hint="args.hint" />`
  })
} satisfies Meta<typeof Input>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Placeholder = createStory({ placeholder: 'isard@isardvdi.com' })
