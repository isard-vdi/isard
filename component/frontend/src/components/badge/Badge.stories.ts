import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { Badge } from '.'

const meta = {
  component: Badge,
  title: 'Badge/Badge',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  },
  argTypes: {
    color: {
      control: 'select',
      options: ['blue', 'red', 'lightred', 'violet', 'indigo']
    },
    content: {
      control: 'text'
    },
    size: {
      control: 'select',
      options: ['md', 'lg']
    },
    shape: {
      control: 'select',
      options: ['pill', 'square']
    },
    icon: {
      control: 'text'
    }
  },
  render: (args) => ({
    components: { Badge },
    setup() {
      return {
        args
      }
    },
    template: `<Badge v-bind="args" />`
  })
} satisfies Meta<typeof Badge>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Story['args']): Story => ({ args })

export const Hidden = createStory({
  content: 'Hidden',
  color: 'gray',
  icon: 'eye-off',
  shape: 'square'
})

export const Visible = createStory({
  content: 'Visible',
  color: 'blue',
  icon: 'eye',
  shape: 'square'
})

export const Downloaded = createStory({
  content: 'Downloaded',
  color: 'green',
  icon: 'dot',
  shape: 'square'
})

export const Failed = createStory({
  content: 'Failed',
  color: 'red',
  icon: 'x',
  shape: 'square'
})

export const Downloading = createStory({
  content: 'Downloading',
  color: 'blue',
  icon: 'dot',
  shape: 'square'
})

export const Full = createStory({
  content: 'Full',
  color: 'lightred',
  icon: 'dot',
  shape: 'pill',
  size: 'lg'
})

export const Medium = createStory({
  content: 'Medium',
  color: 'lightyellow',
  icon: 'dot',
  shape: 'pill',
  size: 'lg'
})

export const Low = createStory({
  content: 'Low',
  color: 'lightgreen',
  icon: 'dot',
  shape: 'pill',
  size: 'lg'
})

export const TextViolet = createStory({
  content: 'Category',
  color: 'violet',
  shape: 'square'
})

export const TextIndigo = createStory({
  content: 'Group',
  color: 'indigo',
  shape: 'square'
})
