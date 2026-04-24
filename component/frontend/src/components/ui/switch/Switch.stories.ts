import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Switch } from '@/components/ui/switch'
import Label from '@/components/ui/label/Label.vue'
import { ref } from 'vue'

const meta: Meta<typeof Switch> = {
  component: Switch,
  title: 'Toggle/Switch',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  },
  argTypes: {
    modelValue: {
      default: false,
      control: 'boolean',
      name: 'checked',
      description: 'Toggle state of the switch'
    },
    disabled: { default: false, control: 'boolean', description: 'Disable user interaction' },
    size: {
      default: 'sm',
      control: { type: 'radio' },
      options: ['sm', 'md'],
      description: 'Size variant: sm (36x20px) or md (44x24px)'
    }
  },
  render: (args = {}) => {
    return {
      components: { Switch },
      setup() {
        return { args }
      },
      template: `<Switch v-model="value" :disabled="disabled" :size="size" />`
    }
  }
}

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    modelValue: true,
    disabled: false,
    size: 'sm'
  },
  render: (args) => ({
    components: { Switch },
    setup: () => ({ args }),
    template: `<Switch v-bind="args" />`
  })
} satisfies Story

export const Interactive: Story = {
  args: { modelValue: true }
}

export const Disabled: Story = {
  render: () => ({
    components: { Switch, Label },
    setup() {
      const checked = ref(true)
      const unchecked = ref(false)
      return { checked, unchecked }
    },
    template: `
      <div class="flex flex-col gap-3">
        <div class="flex items-center gap-2">
          <Switch v-model="unchecked" disabled />
          <Label>Disabled unchecked</Label>
        </div>
        <div class="flex items-center gap-2">
          <Switch v-model="checked" disabled/>
          <Label>Disabled checked</Label>
        </div>
      </div>
    `
  })
}
export const SizeMdStates: Story = {
  render: () => ({
    components: { Switch, Label },
    setup() {
      const states = [
        { label: 'Checked', value: ref(true), disabled: false },
        { label: 'Unchecked', value: ref(false), disabled: false },
        { label: 'Disabled Checked', value: ref(true), disabled: true },
        { label: 'Disabled Unchecked', value: ref(false), disabled: true }
      ]
      return { states }
    },
    template: `
      <div class="flex flex-col gap-4">
        <div v-for="(state, idx) in states" :key="idx" class="flex items-center gap-2">
          <Switch v-model="state.value" size="md" :disabled="state.disabled" />
          <Label>{{ state.label }}</Label>
        </div>
      </div>
    `
  })
}
