import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { Textarea } from '@/components/ui/textarea'

const meta = {
  component: Textarea,
  title: 'Input/Textarea',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=1238-278&t=HEMhgBR8DIWJxCeR-4'
    }
  },
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'Textarea value (v-model)'
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder text'
    },
    hint: {
      control: 'text',
      description: 'Helper text displayed below the textarea'
    },
    destructive: {
      control: 'boolean',
      description: 'Show error state with red border and ring on focus',
      default: false
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the textarea',
      default: false
    },
    errors: {
      control: 'object',
      description: 'Array of error messages to display'
    },
    class: { control: 'text' }
  },
  render: (args) => ({
    components: { Textarea },
    setup() {
      return {
        args
      }
    },
    template: `<div class="w-96"><Textarea :model-value="args.modelValue" :placeholder="args.placeholder" :hint="args.hint" :destructive="args.destructive" :disabled="args.disabled" :errors="args.errors" :class="args.class" /></div>`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof Textarea>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

export const Default = createStory({
  placeholder: 'Enter a description...'
})

export const WithHint = createStory({
  placeholder: 'Enter a description...',
  hint: 'This is a hint text to help user'
})

export const WithHintAndValue = createStory({
  modelValue: 'A little about the company and the team that you’ll be working with.',
  placeholder: 'Enter a description...',
  hint: 'This is a hint text to help user',
  class: 'min-h-32'
})

export const Disabled = createStory({
  placeholder: 'Enter a description...',
  disabled: true
})

export const Destructive = createStory({
  placeholder: 'This textarea is in destructive state',
  destructive: true
})

export const WithError = createStory({
  placeholder: 'Enter a description...',
  errors: ['This is an error message']
})

export const WithErrorAndHint = createStory({
  placeholder: 'Enter a description...',
  hint: 'This is a hint text to help user',
  errors: ['This is an error message']
})
