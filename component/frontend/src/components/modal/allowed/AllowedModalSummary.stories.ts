import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { AllowedModalSummary, type AllowedOption } from '.'

const groups: AllowedOption[] = [
  { value: 'g-1', label: 'Students' },
  { value: 'g-2', label: 'Teachers' }
]

const users: AllowedOption[] = [
  { value: 'u-1', label: 'Anna Bosch' },
  { value: 'u-2', label: 'Joan Puig' },
  { value: 'u-3', label: 'Second year computer science student with a very long name' }
]

const meta = {
  component: AllowedModalSummary,
  title: 'Modal/AllowedModalSummary',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    groups: { control: 'object', description: 'Selected groups, shown as chips.' },
    users: { control: 'object', description: 'Selected users, shown as chips.' },
    allGroups: {
      control: 'boolean',
      description: 'Every group is selected: a single "All groups" chip replaces the list.'
    },
    showGroups: {
      control: 'boolean',
      description: 'When false only users can be selected, so the groups row is omitted.'
    },
    disabled: { control: 'boolean', description: 'Hides the remove buttons.' },
    open: { control: 'boolean', description: 'Whether the chips are shown.' }
  },
  render: (args) => ({
    components: { AllowedModalSummary },
    setup() {
      const open = ref(args.open ?? true)
      const selectedGroups = ref([...(args.groups ?? [])])
      const selectedUsers = ref([...(args.users ?? [])])
      const allGroups = ref(args.allGroups ?? false)
      const removeGroup = (value: string) =>
        (selectedGroups.value = selectedGroups.value.filter((group) => group.value !== value))
      const removeUser = (value: string) =>
        (selectedUsers.value = selectedUsers.value.filter((user) => user.value !== value))
      return { args, open, selectedGroups, selectedUsers, allGroups, removeGroup, removeUser }
    },
    template: `
      <div class="w-[640px]">
        <AllowedModalSummary
          v-bind="args"
          v-model:open="open"
          :groups="selectedGroups"
          :users="selectedUsers"
          :all-groups="allGroups"
          @remove-group="removeGroup"
          @remove-user="removeUser"
          @remove-all-groups="allGroups = false"
        />
      </div>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalSummary>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalSummary>>

export const Expanded: Story = {
  args: { groups, users, open: true }
}

export const Collapsed: Story = {
  args: { groups, users, open: false }
}

export const AllGroups: Story = {
  args: { groups, users: users.slice(0, 1), allGroups: true, open: true }
}

/** Co-owners: only users can be picked. */
export const UsersOnly: Story = {
  args: { groups: [], users, showGroups: false, open: true }
}

export const Empty: Story = {
  args: { groups: [], users: [], open: true }
}

/** Read-only: the chips have no remove button. */
export const Disabled: Story = {
  args: { groups, users, disabled: true, open: true }
}
