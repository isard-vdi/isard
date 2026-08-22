import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Button } from '@/components/ui/button'
import { EmptyState, EMPTY_STATE_IMAGES } from '.'

const meta = {
  component: EmptyState,
  title: 'Page/EmptyState',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    kind: {
      control: 'select',
      options: Object.keys(EMPTY_STATE_IMAGES),
      description: 'Resource the copy and the illustration are taken from.'
    },
    variant: {
      control: 'inline-radio',
      options: ['first-run', 'no-results'],
      description:
        '`first-run` teaches what the resource is and offers to create one; `no-results` only ' +
        'offers a way back from a search or a filter that matched nothing.'
    },
    title: { control: 'text', description: 'Overrides the title resolved from `kind`.' },
    description: {
      control: 'text',
      description: 'Overrides the description resolved from `kind`.'
    },
    searching: { control: 'boolean', description: 'Renders the "Clear search" button.' },
    activeFilters: {
      control: 'number',
      description: 'Renders the "Clear filters" button when above zero.'
    }
  },
  render: (args) => ({
    components: { EmptyState },
    setup: () => ({ args }),
    template: `<EmptyState v-bind="args" />`
  })
} satisfies Meta<typeof EmptyState>

export default meta

type Story = StoryObj<typeof meta>

export const FirstRun: Story = {
  args: { kind: 'templates', variant: 'first-run' }
}

export const FirstRunWithAction: Story = {
  args: { kind: 'desktops', variant: 'first-run' },
  render: (args) => ({
    components: { EmptyState, Button },
    setup: () => ({ args }),
    template: `
      <EmptyState v-bind="args">
        <template #actions>
          <Button icon="plus" size="lg">New desktop</Button>
        </template>
      </EmptyState>
    `
  })
}

export const SharedFirstRun: Story = {
  args: { kind: 'shared-deployments', variant: 'first-run' }
}

export const NoResults: Story = {
  args: { kind: 'media', variant: 'no-results', searching: true }
}

export const NoResultsFiltered: Story = {
  args: { kind: 'templates', variant: 'no-results', searching: true, activeFilters: 1 }
}
