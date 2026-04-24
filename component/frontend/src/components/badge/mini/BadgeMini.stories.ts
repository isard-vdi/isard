import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { BadgeMini } from '.'

const meta = {
  component: BadgeMini,
  title: 'Badge/BadgeMini',
  tags: ['autodocs'],
  argTypes: {
    name: {
      control: 'select',
      options: ['all', 'persistent', 'temporary', 'deployment']
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
