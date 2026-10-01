import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { AllowedModalGroupFilter, type AllowedOption } from '.'

const groups: AllowedOption[] = Array.from({ length: 30 }, (_, index) => ({
  value: `group-${index}`,
  label: `Group ${index + 1}`,
  subLabel: index % 3 === 0 ? `Description for group ${index + 1}` : undefined
}))

const meta = {
  component: AllowedModalGroupFilter,
  title: 'Modal/AllowedModalGroupFilter',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    options: { control: 'object', description: 'Groups that can be picked.' },
    modelValue: { control: 'object', description: 'Ids of the picked groups.' },
    disabled: { control: 'boolean', description: 'Blocks opening the dropdown.' }
  },
  render: (args) => ({
    components: { AllowedModalGroupFilter },
    setup() {
      const selected = ref<string[]>([...(args.modelValue ?? [])])
      return { args, selected }
    },
    template: `
      <div class="flex w-96 justify-end">
        <AllowedModalGroupFilter v-bind="args" v-model="selected" />
      </div>
      <p class="mt-2 text-sm text-gray-warm-600">selected: {{ selected.join(', ') || 'none' }}</p>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalGroupFilter>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalGroupFilter>>

export const Empty: Story = {
  args: { options: groups, modelValue: [] }
}

/** The trigger switches to brand colours and shows how many groups are picked. */
export const WithSelection: Story = {
  args: { options: groups, modelValue: ['group-0', 'group-4'] }
}

export const Disabled: Story = {
  args: { options: groups, modelValue: ['group-0'], disabled: true }
}
