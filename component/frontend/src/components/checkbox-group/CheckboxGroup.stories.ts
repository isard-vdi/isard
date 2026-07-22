import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { CheckboxGroup } from '@/components/checkbox-group'

const meta = {
  component: CheckboxGroup,
  title: 'Checkbox/CheckboxGroup',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/kZGlXBMDzC0kVb3BMl7j7x/NAOMI--ISARD-Design-system-Cliente?node-id=124-2838&m=dev'
    }
  },
  argTypes: {
    kind: {
      control: 'select',
      options: ['card', 'text', 'image', 'featured-icon'],
      defaultValue: 'featured-icon'
    },
    type: {
      control: 'select',
      options: ['multiple', 'single'],
      defaultValue: 'multiple'
    },
    checkType: {
      control: 'select',
      options: ['checkbox', 'radio'],
      defaultValue: 'checkbox'
    },
    loading: {
      control: 'boolean',
      defaultValue: false
    },
    modelValue: {
      control: 'text'
    },
    items: {
      control: 'object'
    }
  },
  render: (args) => ({
    components: { CheckboxGroup },
    setup() {
      const modelValue = ref(args.modelValue)

      // Watch for changes from Storybook controls
      watch(
        () => args.modelValue,
        (newValue) => {
          modelValue.value = newValue
        }
      )

      const handleUpdate = (value: string | string[]) => {
        modelValue.value = value
        args.modelValue = value
      }

      return {
        args,
        modelValue,
        handleUpdate
      }
    },
    template:
      '<CheckboxGroup v-bind="args" v-model="modelValue" @update:modelValue="handleUpdate" />'
  })
} satisfies Meta<typeof CheckboxGroup>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    items: [
      {
        title: 'Option 1',
        description: 'Description for option 1',
        value: 'option1',
        icon: 'monitor-01'
      },
      {
        title: 'Option 2',
        description: 'Description for option 2',
        value: 'option2',
        icon: 'face-smile'
      },
      {
        title: 'Option 3',
        description: 'Description for option 3',
        value: 'option3',
        icon: 'clock'
      }
    ],
    modelValue: 'option1',
    kind: 'featured-icon',
    type: 'single',
    checkType: 'radio',
    loading: false
  }
}

export const Loading: Story = {
  args: {
    items: [
      {
        title: 'Option 1',
        description: 'Description for option 1',
        value: 'option1',
        icon: 'monitor-01'
      },
      {
        title: 'Option 2',
        description: 'Description for option 2',
        value: 'option2',
        icon: 'face-smile'
      },
      {
        title: 'Option 3',
        description: 'Description for option 3',
        value: 'option3',
        icon: 'clock'
      }
    ],
    modelValue: '',
    kind: 'featured-icon',
    type: 'single',
    checkType: 'radio',
    loading: true
  }
}

export const DesktopPersistencySelection: Story = {
  args: {
    items: [
      {
        color: 'persistent',
        title: 'Persistent',
        description: 'A persistent desktop retains your settings and data between sessions.',
        value: 'persistent',
        icon: 'monitor-02'
      },
      {
        color: 'temporary',
        title: 'Non-persistent',
        description: 'A non-persistent desktop resets to its original state after each session.',
        value: 'nonpersistent',
        icon: 'clock'
      }
    ],
    modelValue: 'persistent',
    kind: 'featured-icon',
    type: 'single',
    checkType: 'radio',
    loading: false
  }
}
