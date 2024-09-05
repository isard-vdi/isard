import type { Meta, StoryObj } from '@storybook/vue3'
import { NavbarItem } from '@/components/navbar'

const meta = {
  component: NavbarItem,
  title: 'NavbarItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=1152-89351'
    }
  },
  argTypes: {
    current: { control: 'boolean' },
    collapsed: { control: 'boolean' }
  },
  render: (args) => ({
    components: { NavbarItem },
    setup() {
      return {
        args
      }
    },
    template: `
      <NavbarItem
        :icon="args.icon"
        :label="args.label"
        :current="args.current"
        :collapsed="args.collapsed"
      />`
  })
} satisfies Meta<typeof NavbarItem>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  icon: 'bar-chart-01',
  label: 'Dashboard'
})

export const Current = createStory({
  icon: 'bar-chart-01',
  label: 'Dashboard',
  current: true
})
