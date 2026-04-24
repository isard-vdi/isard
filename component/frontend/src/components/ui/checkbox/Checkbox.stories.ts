import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { Checkbox } from '@/components/ui/checkbox'

const meta = {
  component: Checkbox,
  title: 'Checkbox/Checkbox',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/kZGlXBMDzC0kVb3BMl7j7x/NAOMI--ISARD-Design-system-Cliente?node-id=1097-63652'
    }
  },
  argTypes: {
    modelValue: {
      control: 'select',
      options: [true, false, 'indeterminate']
    },
    indeterminate: {
      control: 'boolean',
      defaultValue: false
    },
    size: {
      control: 'select',
      options: ['sm', 'md'],
      defaultValue: 'md'
    },
    type: {
      control: 'select',
      options: ['checkbox', 'radio'],
      defaultValue: 'checkbox'
    },
    title: {
      control: 'text'
    },
    subtitle: {
      control: 'text'
    },
    textPosition: {
      control: 'select',
      options: ['before', 'after'],
      defaultValue: 'after'
    }
  },
  render: (args) => ({
    components: { Checkbox },
    setup() {
      const modelValue = ref(args.modelValue)

      // Watch for changes from Storybook controls
      watch(
        () => args.modelValue,
        (newValue) => {
          modelValue.value = newValue
        }
      )

      return {
        args,
        modelValue
      }
    },
    template: `<Checkbox v-model="modelValue" :size="args.size" :type="args.type" :title="args.title" :subtitle="args.subtitle" :textPosition="args.textPosition" :indeterminate="args.indeterminate" :disabled="args.disabled" />`
  })
} satisfies Meta<typeof Checkbox>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  modelValue: false
})
export const Checked = createStory({
  modelValue: true
})
export const Indeterminate = createStory({
  modelValue: 'indeterminate',
  indeterminate: true
})
export const Disabled = createStory({
  modelValue: false,
  disabled: true
})
export const CheckedDisabled = createStory({
  modelValue: true,
  disabled: true
})
export const IndeterminateDisabled = createStory({
  modelValue: 'indeterminate',
  indeterminate: true,
  disabled: true
})
export const Radio = createStory({
  modelValue: false,
  type: 'radio'
})
export const RadioChecked = createStory({
  modelValue: true,
  type: 'radio'
})
export const RadioIndeterminate = createStory({
  modelValue: 'indeterminate',
  type: 'radio',
  indeterminate: true
})
export const RadioDisabled = createStory({
  modelValue: false,
  type: 'radio',
  disabled: true
})
export const RadioCheckedDisabled = createStory({
  modelValue: true,
  type: 'radio',
  disabled: true
})
export const RadioIndeterminateDisabled = createStory({
  modelValue: 'indeterminate',
  type: 'radio',
  indeterminate: true,
  disabled: true
})
export const SmallSize = createStory({
  modelValue: false,
  size: 'sm'
})
export const RadioSmallSize = createStory({
  modelValue: false,
  size: 'sm',
  type: 'radio'
})
export const MediumSize = createStory({
  modelValue: false,
  size: 'md'
})
export const RadioMediumSize = createStory({
  modelValue: false,
  size: 'md',
  type: 'radio'
})
export const WithTitleAndSubtitle = createStory({
  modelValue: false,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.'
})
export const CheckedWithTitleAndSubtitle = createStory({
  modelValue: true,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.'
})
export const DisabledWithTitleAndSubtitle = createStory({
  modelValue: false,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.',
  disabled: true
})
export const DisabledCheckedWithTitleAndSubtitle = createStory({
  modelValue: true,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.',
  disabled: true
})
export const TextBeforeCheckbox = createStory({
  modelValue: false,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.',
  textPosition: 'before'
})
export const TextAfterCheckbox = createStory({
  modelValue: false,
  title: 'Remember me',
  subtitle: 'Save my login details for next time.',
  textPosition: 'after'
})
