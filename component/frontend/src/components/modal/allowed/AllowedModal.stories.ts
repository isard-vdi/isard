import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import AllowedModal from './AllowedModal.vue'

const meta = {
  component: AllowedModal,
  title: 'Modal/AllowedModal',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    open: {
      control: 'boolean',
      description: 'Whether the modal is open.'
    },
    loading: {
      control: 'boolean',
      description: 'Whether the modal is in a loading state.'
    },
    title: {
      control: 'text',
      description: 'Title of the modal.'
    },
    description: {
      control: 'text',
      description: 'Description text of the modal.'
    },
    groups: {
      control: 'object',
      description: 'Object containing available and selected groups.'
    },
    users: {
      control: 'object',
      description: 'Object containing available and selected users.'
    }
  },
  render: (args) => ({
    components: { AllowedModal },
    setup() {
      return { args }
    },
    template: `<AllowedModal v-bind="args" @close="args.open = false" @save="(val) => { console.log('Saved:', val) }" />`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModal>>

export default meta

type Story = StoryObj<typeof meta>
const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  open: true,
  loading: false,
  title: 'Manage Allowed Entities',
  description: 'Select the users and groups that are allowed access.',
  groups: {
    available: [
      { label: 'Admins', subLabel: 'Administrators with full access', value: 'admins' },
      { label: 'Editors', subLabel: 'Users who can edit content', value: 'editors' },
      { label: 'Viewers', subLabel: 'Users who can view content only', value: 'viewers' },
      { label: 'Guests', subLabel: 'Temporary access users', value: 'guests' },
      { label: 'Managers', subLabel: 'Users with managerial roles', value: 'managers' }
    ],
    selected: ['editors'],
    indeterminate: ['viewers','guests']
  },
  users: {
    available: [
      { label: 'Esther', avatar: `${window.location.origin}/favicon.ico`, value: 'esther' },
      { label: 'Celia', value: 'celia' },
      { label: 'Raquel', value: 'raquel' },
      { label: 'David', value: 'david' },
      { label: 'Sophia', value: 'sophia' }
    ],
    selected: ['celia','david']
  }
})