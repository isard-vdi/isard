import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { AllowedModalItem } from '.'

const meta = {
  component: AllowedModalItem,
  title: 'Modal/AllowedModalItem',
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
    },
    active: {
      control: 'boolean',
      description: 'Highlights the row, e.g. the group whose users are currently shown.'
    },
    disabled: {
      control: 'boolean',
      description: 'Whether the item can be toggled.'
    }
  },
  render: (args) => ({
    components: { AllowedModalItem },
    setup() {
      // The item is fully controlled, so the story has to own the state and echo it back.
      const checked = ref(args.checked ?? false)
      watch(
        () => args.checked,
        (value) => (checked.value = value ?? false)
      )
      // The row click is a separate event from the checkbox: it does not select.
      const selects = ref(0)
      return { args, checked, selects }
    },
    template: `
      <div class="w-96">
        <AllowedModalItem
          v-bind="args"
          :checked="checked"
          @update:checked="checked = $event"
          @select="selects++"
        />
        <p class="mt-2 px-2 text-sm text-gray-warm-600">row clicked {{ selects }} time(s)</p>
      </div>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalItem>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalItem>>

export const Primary: Story = {
  args: {
    label: 'Group A',
    subLabel: 'This is group A',
    value: 'group-a',
    icon: 'users-01'
  }
}

export const Checked: Story = {
  args: {
    label: 'Group B',
    subLabel: 'This is group B',
    value: 'group-b',
    icon: 'users-01',
    checked: true
  }
}

export const Indeterminate: Story = {
  args: {
    label: 'Group C',
    subLabel: 'This is group C',
    value: 'group-c',
    icon: 'users-01',
    checked: 'indeterminate'
  }
}

export const Active: Story = {
  args: {
    label: 'Group D',
    subLabel: 'The group whose users are currently shown',
    value: 'group-d',
    icon: 'users-01',
    active: true
  }
}

export const Disabled: Story = {
  args: {
    label: 'Group E',
    subLabel: 'This is group E',
    value: 'group-e',
    icon: 'users-01',
    checked: true,
    disabled: true
  }
}

export const WithAvatar: Story = {
  args: {
    label: 'User John Doe',
    subLabel: 'jdoe',
    avatar: `${window.location.origin}/favicon.ico`,
    value: 'user-john-doe'
  }
}

export const WithAvatarChecked: Story = {
  args: {
    label: 'User Jane Smith',
    subLabel: 'jsmith',
    avatar: `${window.location.origin}/favicon.ico`,
    value: 'user-jane-smith',
    checked: true
  }
}

/** No photo: the avatar falls back to the initials. */
export const WithAvatarFallback: Story = {
  args: {
    label: 'Alex Johnson',
    subLabel: 'ajohnson',
    avatar: '',
    value: 'user-alex-johnson'
  }
}

/** A long label must truncate instead of pushing the action out of the row. */
export const WithActionAndLongLabel: Story = {
  render: (args) => ({
    components: { AllowedModalItem, Button },
    setup() {
      const checked = ref(args.checked ?? false)
      const selects = ref(0)
      return { args, checked, selects }
    },
    template: `
      <div class="w-96">
        <AllowedModalItem
          v-bind="args"
          :checked="checked"
          @update:checked="checked = $event"
          @select="selects++"
        >
          <template #actions>
            <Button
              icon="arrow-circle-broken-right"
              hierarchy="link-color"
              @click.stop="selects++"
            />
          </template>
        </AllowedModalItem>
        <p class="mt-2 px-2 text-sm text-gray-warm-600">row clicked {{ selects }} time(s)</p>
      </div>
    `
  }),
  args: {
    label: 'Second year computer science students, afternoon shift, building B',
    subLabel: 'Every student enrolled in the 2025/2026 afternoon shift of the second year',
    value: 'group-long',
    icon: 'users-01'
  }
}
