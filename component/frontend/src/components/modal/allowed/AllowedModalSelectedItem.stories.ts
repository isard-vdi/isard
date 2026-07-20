import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { AllowedModalSelectedItem } from '.'

const meta = {
  component: AllowedModalSelectedItem,
  title: 'Modal/AllowedModalSelectedItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: ''
    },
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    checked: {
      control: 'select',
      options: [true, false, 'indeterminate'],
      description: 'Checked state of the item.'
    },
    label: {
      control: 'text',
      description: 'Label for the item.'
    },
    subLabel: {
      control: 'text',
      description: 'SubLabel for the item.'
    },
    avatar: {
      control: 'text',
      description: 'Avatar URL for the item.'
    },
    icon: {
      control: 'text',
      description: 'Icon name for the item.'
    },
    value: {
      control: 'text',
      description: 'Value of the item.'
    }
  },
  render: (args) => ({
    components: { AllowedModalSelectedItem },
    setup() {
      return {
        args
      }
    },
    template: '<AllowedModalSelectedItem v-model="modelValue" v-bind="args" />'
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalSelectedItem>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalSelectedItem>>

export const Primary: Story = {
  args: {
    label: 'Group A',
    subLabel: 'This is group A',
    value: 'group-a'
  }
}

export const Checked: Story = {
  args: {
    label: 'Group B',
    subLabel: 'This is group B',
    value: 'group-b',
    checked: true
  }
}

export const Indeterminate: Story = {
  args: {
    label: 'Group C',
    subLabel: 'This is group C',
    value: 'group-c',
    checked: 'indeterminate'
  }
}

export const WithAvatar: Story = {
  args: {
    label: 'User John Doe',
    subLabel: 'This is John Doe',
    avatar: `${window.location.origin}/favicon.ico`,
    icon: '',
    value: 'user-john-doe'
  }
}

export const WithAvatarChecked: Story = {
  args: {
    label: 'User Jane Smith',
    subLabel: 'This is Jane Smith',
    avatar: `${window.location.origin}/favicon.ico`,
    icon: '',
    value: 'user-jane-smith',
    checked: true
  }
}

export const WithAvatarIndeterminate: Story = {
  args: {
    label: 'User Alex Johnson',
    subLabel: 'This is Alex Johnson',
    avatar: `${window.location.origin}/favicon.ico`,
    icon: '',
    value: 'user-alex-johnson',
    checked: 'indeterminate'
  }
}