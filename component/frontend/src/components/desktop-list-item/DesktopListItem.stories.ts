import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import DesktopListItem from './DesktopListItem.vue'

const meta = {
  component: DesktopListItem,
  title: 'ListItem/DesktopListItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma'
    },
    layout: 'centered'
  },
  argTypes: {
    number: {
      control: 'number',
      description: 'Desktop number identifier'
    },
    name: {
      control: 'text',
      description: 'Name of the desktop'
    },
    description: {
      control: 'text',
      description: 'Optional description of the desktop'
    },
    image: {
      control: 'text',
      description: 'Optional image URL for desktop preview'
    },
    hardware: {
      control: 'object',
      description: 'Hardware specifications for the desktop'
    },
    'update:image': { action: 'update:image' },
    'update:hardware': { action: 'update:hardware' }
  },
  render: (args) => ({
    components: { DesktopListItem },
    setup() {
      return { args }
    },
    template: `<div><DesktopListItem v-bind="args" /></div>`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DesktopListItem>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Partial<ComponentPropsAndSlots<typeof DesktopListItem>>): Story => ({
  args
})

export const Default = createStory({
  number: 1,
  hardware: {
    cpu: 2,
    ram: 4 * 1024,
    boot: 'disk',
    isos: ['Windows-10.iso'],
    networkInterfaces: ['eth0']
  }
})

export const CompleteDesktop = createStory({
  number: 2,
  name: 'Design Lab',
  description: 'Powerful workstation for graphic design and 3D modeling',
  hardware: {
    cpu: 8,
    ram: 16 * 1024,
    boot: 'disk',
    isos: ['Ubuntu-22.04.iso', 'Windows-11.iso'],
    networkInterfaces: ['eth0', 'wlan0']
  }
})

// Desktop with long content to test overflow handling
export const LongContent = createStory({
  number: 5,
  name: 'Desktop with a very long name that might cause overflow issues in some containers',
  description:
    'This desktop has a very long description that contains many details about its purpose and configuration. It should test how the component handles text overflow and wrapping for long content.',
  hardware: {
    cpu: 4,
    ram: 8 * 1024,
    boot: 'CD/DVD',
    isos: [
      'Very-long-iso-name-with-detailed-version-information-1.0.0.iso',
      'Another-very-long-iso-name-2.0.0.iso'
    ],
    networkInterfaces: ['network-interface-with-long-name-1', 'network-interface-with-long-name-2']
  }
})
