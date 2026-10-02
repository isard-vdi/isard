import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { AllowedModalGroupSelect, type AllowedOption } from '.'

const groups: AllowedOption[] = Array.from({ length: 30 }, (_, index) => ({
  value: `group-${index}`,
  label: `Group ${index + 1}`
}))

const meta = {
  component: AllowedModalGroupSelect,
  title: 'Modal/AllowedModalGroupSelect',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    options: { control: 'object', description: 'Groups that can be picked.' },
    modelValue: { control: 'text', description: 'Id of the picked group, or null for all.' },
    disabled: { control: 'boolean', description: 'Blocks opening the dropdown.' }
  },
  render: (args) => ({
    components: { AllowedModalGroupSelect },
    setup() {
      const selected = ref<string | null>(args.modelValue ?? null)
      return { args, selected }
    },
    template: `
      <div class="w-48">
        <AllowedModalGroupSelect v-bind="args" v-model="selected" />
      </div>
      <p class="mt-2 text-sm text-gray-warm-600">selected: {{ selected ?? 'all' }}</p>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalGroupSelect>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalGroupSelect>>

export const AllGroups: Story = {
  args: { options: groups, modelValue: null }
}

export const WithSelection: Story = {
  args: { options: groups, modelValue: 'group-4' }
}

export const Disabled: Story = {
  args: { options: groups, modelValue: 'group-4', disabled: true }
}
