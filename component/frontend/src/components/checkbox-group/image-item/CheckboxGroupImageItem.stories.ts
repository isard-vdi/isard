import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { CheckboxGroupImageItem } from '.'
import rdpBrowser from '@/assets/img/viewers/rdp-browser.svg'
import rdp from '@/assets/img/viewers/rdp.svg'
import spice from '@/assets/img/viewers/spice.svg'
import vncBrowser from '@/assets/img/viewers/vnc-browser.svg'

const meta: Meta<typeof CheckboxGroupImageItem> = {
  component: CheckboxGroupImageItem,
  title: 'Checkbox/CheckboxGroupImageItem',
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
      description: 'Item data with image, label, and value'
    }
  },
  render: (args) => ({
    components: { CheckboxGroupImageItem },
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
      '<CheckboxGroupImageItem v-bind="args" :is-selected="isSelected" @check="handleCheck" />'
  })
}

export default meta
type Story = StoryObj<typeof meta>

export const RDPBrowser: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      image: rdpBrowser,
      label: 'RDP Browser',
      value: 'rdp-browser'
    }
  }
}

export const Spice: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      image: spice,
      label: 'SPICE',
      value: 'spice'
    }
  }
}

export const Selected: Story = {
  args: {
    loading: false,
    isSelected: true,
    disabled: false,
    item: {
      image: rdp,
      label: 'RDP',
      value: 'rdp-browser'
    }
  }
}

export const Loading: Story = {
  args: {
    loading: true,
    isSelected: false,
    disabled: false,
    item: {
      image: rdp,
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
      image: vncBrowser,
      label: 'VNC Browser',
      value: 'vnc-browser'
    }
  }
}
