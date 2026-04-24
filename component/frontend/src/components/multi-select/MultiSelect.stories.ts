import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { MultiSelect } from '.'
// import type Tag as MultiSelectTag from './MultiSelect.vue'

const meta = {
  component: MultiSelect,
  title: 'Dropdown/MultiSelect',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=18-0&p=f&t=1WbtG9kifoQ2eHdq-0'
    },
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    tags: {
      control: 'object',
      description: 'Array of objects representing the dropdown menu items.'
    },
    preselectedTags: {
      control: 'object',
      description:
        'Array of objects representing the tags that are already selected when the component is mounted.'
    },
    label: {
      control: 'text',
      description: 'Label for the component.'
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder for the input field.'
    },
    notFoundText: {
      control: 'text',
      description: 'Text to display when no results are found.'
    }
  },
  render: (args) => ({
    components: { MultiSelect },
    setup() {
      return { args }
    },
    template: `
      <div class="h-120 w-full">
        <MultiSelect
          :tags="args.tags"
          :preselectedTags="args.preselectedTags"
          :label="args.label"
          :placeholder="args.placeholder"
          :notFoundText="args.notFoundText"
        />
      </div>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof MultiSelect>>

export default meta

type Story = StoryObj<typeof meta>
const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

const usersList = [
  { id: '0000', label: 'User 1', avatar: `${window.location.origin}/favicon.ico` },
  { id: '0001', label: 'User 2', avatar: '' },
  { id: '0002', label: 'User 3', avatar: '' },
  { id: '0003', label: 'User 4', avatar: '' },
  { id: '0004', label: 'User 5', avatar: '' },
  { id: '0005', label: 'User 6', avatar: '' },
  { id: '0006', label: 'User 7', avatar: '' },
  { id: '0007', label: 'User 8', avatar: '' }
]

const groupsList = [
  { id: '0001', label: 'Group 1', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0002', label: 'Group 2', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0003', label: 'Group 3', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0004', label: 'Group 4', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0005', label: 'Group 5', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0006', label: 'Group 6', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0007', label: 'Group 7', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0008', label: 'Group 8', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0009', label: 'Group 9', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0010', label: 'Group 10', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0011', label: 'Group 11', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0012', label: 'Group 12', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0013', label: 'Group 13', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0014', label: 'Group 14', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0015', label: 'Group 15', icon: 'users-01', subLabel: 'Category 1' },
  { id: '0016', label: 'Group 16', icon: 'users-01', subLabel: 'Category 1' },
  { id: '1001', label: 'Group 1', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1002', label: 'Group 2', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1003', label: 'Group 3', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1004', label: 'Group 4', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1005', label: 'Group 5', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1006', label: 'Group 6', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1007', label: 'Group 7', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1008', label: 'Group 8', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1009', label: 'Group 9', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1010', label: 'Group 10', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1011', label: 'Group 11', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1012', label: 'Group 12', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1013', label: 'Group 13', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1014', label: 'Group 14', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1015', label: 'Group 15', icon: 'users-01', subLabel: 'Category 2' },
  { id: '1016', label: 'Group 16', icon: 'users-01', subLabel: 'Category 2' }
]

export const UserSelect = createStory({
  tags: usersList,
  preselectedTags: [usersList[0], usersList[1], usersList[2], usersList[3]],
  label: 'Users',
  placeholder: 'Search users',
  notFoundText: 'No users found with that name'
})

export const GroupSelect = createStory({
  tags: groupsList,
  preselectedTags: [groupsList[0], groupsList[1]],
  label: 'Groups',
  placeholder: 'Search groups'
})
