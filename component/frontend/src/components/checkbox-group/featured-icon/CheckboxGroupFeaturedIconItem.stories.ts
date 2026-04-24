import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { CheckboxGroupFeaturedIconItem } from '@/components/checkbox-group/featured-icon'

const meta = {
  component: CheckboxGroupFeaturedIconItem,
  title: 'Checkbox/CheckboxGroupFeaturedIconItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/kZGlXBMDzC0kVb3BMl7j7x/NAOMI--ISARD-Design-system-Cliente?node-id=124-2838&m=dev'
    }
  },
  argTypes: {
    loading: {
      control: 'boolean',
      defaultValue: false
    },
    checkType: {
      control: 'select',
      options: ['checkbox', 'radio'],
      defaultValue: 'checkbox'
    },
    isSelected: {
      control: 'boolean',
      defaultValue: false
    },
    disabled: {
      control: 'boolean',
      defaultValue: false
    },
    item: {
      control: 'object'
    }
  },
  render: (args) => ({
    components: { CheckboxGroupFeaturedIconItem },
    setup() {
      const isSelected = ref(args.isSelected)

      // Watch for changes from Storybook controls
      watch(
        () => args.isSelected,
        (newValue) => {
          isSelected.value = newValue
        }
      )

      const handleCheck = () => {
        isSelected.value = !isSelected.value
        args.isSelected = isSelected.value
      }

      return {
        args,
        isSelected,
        handleCheck
      }
    },
    template:
      '<CheckboxGroupFeaturedIconItem v-bind="args" :is-selected="isSelected" @check="handleCheck" />'
  })
} satisfies Meta<typeof CheckboxGroupFeaturedIconItem>

export default meta
type Story = StoryObj<typeof meta>

export const TemporaryDesktop: Story = {
  args: {
    checkType: 'radio',
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      color: 'temporary',
      icon: 'clock',
      title: 'Temporary',
      description: 'Temporary desktops do not save any data',
      value: 'temporary'
    }
  }
}

export const SelectedTemporaryDesktop: Story = {
  args: {
    checkType: 'radio',
    loading: false,
    isSelected: true,
    disabled: false,
    item: {
      color: 'temporary',
      icon: 'clock',
      title: 'Temporary',
      description: 'Temporary desktops do not save any data',
      value: 'temporary'
    }
  }
}

export const PersistentDesktop: Story = {
  args: {
    checkType: 'radio',
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      color: 'persistent',
      icon: 'monitor-02',
      title: 'Persistent',
      description: 'Persistent desktops save all the data',
      value: 'persistent'
    }
  }
}

export const SelectedPersistentDesktop: Story = {
  args: {
    checkType: 'radio',
    loading: false,
    isSelected: true,
    disabled: false,
    item: {
      color: 'persistent',
      icon: 'monitor-02',
      title: 'Persistent',
      description: 'Persistent desktops save all the data',
      value: 'persistent'
    }
  }
}

export const LoadingState: Story = {
  args: {
    checkType: 'radio',
    loading: true,
    isSelected: false,
    disabled: false,
    item: {
      color: 'persistent',
      icon: 'monitor-02',
      title: 'Persistent',
      description: 'Persistent desktops save all the data',
      value: 'persistent'
    }
  }
}

export const DisabledState: Story = {
  args: {
    checkType: 'radio',
    loading: false,
    isSelected: false,
    disabled: true,
    item: {
      color: 'persistent',
      icon: 'monitor-02',
      title: 'Persistent',
      description: 'Persistent desktops save all the data',
      value: 'persistent'
    }
  }
}
