import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import DropdownButton from './DropdownButton.vue'

const meta = {
  component: DropdownButton,
  title: 'Dropdown/DropdownButton',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=18-0&p=f&t=1WbtG9kifoQ2eHdq-0'
    }
  },
  argTypes: {
    menuContent: {
      control: 'object',
      description: 'Array of objects representing the dropdown menu items.'
    }
  },
  render: (args) => ({
    components: { DropdownButton },
    setup() {
      return { args }
    },
    template: `
      <DropdownButton 
        :menuContent="args.menuContent"
      />
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DropdownButton>>

export default meta

type Story = StoryObj<typeof meta>
const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

const deploymentMenuContent = [
  { icon: 'edit-01', text: 'Edit', textKey: 'components.menu.deployment.edit' },
  { icon: 'download-02', text: 'Download', textKey: 'components.menu.deployment.download' },
  { icon: 'link-01', text: 'Copy Link', textKey: 'components.menu.deployment.link' },
  { icon: 'refresh-cw-04', text: 'Recreate', textKey: 'components.menu.deployment.recreate' },
  { icon: 'calendar', text: 'Book', textKey: 'components.menu.deployment.book' },
  { icon: 'trash-04', text: 'Delete', textKey: 'components.menu.deployment.delete' }
]

const labMenuContent = [
  { icon: 'edit-01', text: 'Edit', textKey: 'components.menu.lab.edit' },
  { icon: 'colors', text: 'Create', textKey: 'components.menu.lab.create' },
  { icon: 'calendar', text: 'Book', textKey: 'components.menu.lab.book' },
  { icon: 'trash-04', text: 'Delete', textKey: 'components.menu.lab.delete' }
]

export const Deployment = createStory({
  menuContent: deploymentMenuContent
})

export const Lab = createStory({
  menuContent: labMenuContent
})
