import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { CheckboxGroupTextItem } from '.'

const meta: Meta<typeof CheckboxGroupTextItem> = {
  component: CheckboxGroupTextItem,
  title: 'Checkbox/CheckboxGroupTextItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=124-2838&t=eC4rJRHjmtfpH7YL-4'
    }
  },
  argTypes: {
    loading: {
      control: 'boolean',
      defaultValue: false,
      description: 'Show loading skeleton, uncheckable'
    },
    isSelected: {
      control: 'boolean',
      defaultValue: false,
      description: 'Whether the item is selected'
    },
    disabled: {
      control: 'boolean',
      defaultValue: false,
      description: 'Disable user interaction'
    },
    item: {
      control: 'object',
      description: 'Item data with icon (optional), label and value'
    }
  },
  render: (args) => ({
    components: { CheckboxGroupTextItem },
    setup() {
      const isSelected = ref(args.isSelected)
      watch(
        () => args.isSelected,
        (newValue) => {
          isSelected.value = newValue
        }
      )

      const handleCheck = () => {
        isSelected.value = !isSelected.value
      }

      return {
        args,
        isSelected,
        handleCheck
      }
    },
    template:
      '<CheckboxGroupTextItem v-bind="args" :is-selected="isSelected" @check="handleCheck" />'
  })
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      label: 'Virtio',
      value: 'virtio'
    }
  }
}

export const WithIcon: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      icon: 'hdd-02',
      label: 'Virtio',
      value: 'virtio'
    }
  }
}

export const SelectedWithIcon: Story = {
  args: {
    loading: false,
    isSelected: true,
    disabled: false,
    item: {
      icon: 'wires',
      label: 'VGA',
      value: 'vga'
    }
  }
}

export const Loading: Story = {
  args: {
    loading: true,
    isSelected: false,
    disabled: false,
    item: {
      label: 'Loading...',
      value: 'loading'
    }
  }
}

export const Disabled: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: true,
    item: {
      icon: 'wires',
      label: 'VGA',
      value: 'vga'
    }
  }
}
