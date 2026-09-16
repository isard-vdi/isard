import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { BadgeMini } from '.'

const meta = {
  component: BadgeMini,
  title: 'Badge/BadgeMini',
  tags: ['autodocs'],
  argTypes: {
    name: {
      control: 'select',
      options: [
        'all',
        'persistent',
        'temporary',
        'deployment',
        'status-all',
        'status-started',
        'status-stopped'
      ]
    },
    value: {
      control: 'text'
    },
    selected: {
      control: 'boolean'
    }
  },
  render: (args) => ({
    components: { BadgeMini },
    setup() {
      return {
        args
      }
    },
    template: `<BadgeMini v-bind="args" />
    `
  })
} satisfies Meta<typeof BadgeMini>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Story['args']): Story => ({ args })

export const All = createStory({
  value: '10',
  name: 'all'
})

export const Persistent = createStory({
  value: '4',
  name: 'persistent'
})

export const Temporary = createStory({
  value: '4',
  name: 'temporary'
})

export const Deployment = createStory({
  value: '2',
  name: 'deployment'
})

export const AllSelected = createStory({
  value: '10',
  name: 'all',
  selected: true
})

export const PersistentSelected = createStory({
  value: '4',
  name: 'persistent',
  selected: true
})

export const TemporarySelected = createStory({
  value: '4',
  name: 'temporary',
  selected: true
})

export const DeploymentSelected = createStory({
  value: '2',
  name: 'deployment',
  selected: true
})

export const StatusAll = createStory({
  value: '10',
  name: 'status-all'
})

export const StatusStarted = createStory({
  value: '6',
  name: 'status-started'
})

export const StatusStopped = createStory({
  value: '4',
  name: 'status-stopped'
})

export const StatusAllSelected = createStory({
  value: '10',
  name: 'status-all',
  selected: true
})

export const StatusStartedSelected = createStory({
  value: '6',
  name: 'status-started',
  selected: true
})

export const StatusStoppedSelected = createStory({
  value: '4',
  name: 'status-stopped',
  selected: true
})
