import type { Meta, StoryObj } from '@storybook/vue3'
import { Alert, AlertTitle, AlertDescription } from '.'

const meta = {
  component: Alert,
  title: 'Alert',
  tags: ['autodocs'],
  render: (args) => ({
    components: { Alert, AlertTitle, AlertDescription },
    setup() {
      return {
        args
      }
    },
    template: `
      <Alert :variant="args.variant">
        <AlertTitle v-if="args.title !== null">{{ args.title }}</AlertTitle>
        <AlertDescription>{{ args.description }}</AlertDescription>
      </Alert>
    `
  })
} satisfies Meta<typeof Alert> & {
  title?: string
  description: string
}

export default meta
type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  title: 'Alert title',
  description: 'This is an alert description'
})

export const Description = createStory({
  description: Default.args?.description
})

export const Destructive = createStory({ ...Default.args, variant: 'destructive' })
