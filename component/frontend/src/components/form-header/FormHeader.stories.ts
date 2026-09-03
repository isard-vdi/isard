import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { FormHeader } from './index'
import { StepperForm } from '@/components/stepper-form'

const steps = [
  { step: 1, title: 'Template' },
  { step: 2, title: 'Settings' }
]

const meta: Meta<typeof FormHeader> = {
  title: 'FormHeader/FormHeader',
  component: FormHeader,
  tags: ['autodocs'],
  argTypes: {
    cancelTo: {
      control: 'text',
      description: 'Route the cancel action navigates to when the user leaves the form'
    },
    cancelLabel: {
      control: 'text',
      description: 'Says what is being cancelled, so it is not read as a step back'
    },
    confirmCancel: {
      control: 'boolean',
      description: 'Ask for confirmation before leaving, so filled in data is not lost by mistake'
    },
    showPrevious: {
      control: 'boolean',
      description: 'Show the previous step button. Only for multi step forms.'
    },
    nextLabel: { control: 'text' },
    nextDisabled: { control: 'boolean' },
    nextPending: { control: 'boolean' },
    nextTooltip: {
      control: 'object',
      description: 'Explains why the primary action is disabled'
    }
  }
}

export default meta

type Story = StoryObj<typeof meta>

export const Wizard: Story = {
  args: {
    cancelTo: '/desktops',
    showPrevious: true,
    confirmCancel: true,
    nextLabel: 'Create desktop'
  },
  render: (args) => ({
    components: { FormHeader, StepperForm },
    setup() {
      return { args, steps }
    },
    template: `
      <div class="bg-base-background p-8">
        <FormHeader v-bind="args">
          <template #stepper>
            <div class="shrink-0 w-95">
              <StepperForm :model-value="2" :steps="steps" />
            </div>
          </template>
        </FormHeader>
      </div>
    `
  })
}

export const FirstStep: Story = {
  ...Wizard,
  args: {
    ...Wizard.args,
    showPrevious: false,
    confirmCancel: false,
    nextLabel: 'Next'
  }
}

export const NextDisabled: Story = {
  ...Wizard,
  args: {
    ...Wizard.args,
    nextDisabled: true,
    nextTooltip: {
      title: 'Missing required fields',
      description: 'Fill in every required field to continue'
    }
  }
}

export const WithoutSteps: Story = {
  args: {
    cancelTo: '/templates',
    cancelLabel: 'Cancel editing',
    nextLabel: 'Save'
  },
  render: (args) => ({
    components: { FormHeader },
    setup() {
      return { args }
    },
    template: `
      <div class="bg-base-background p-8">
        <FormHeader v-bind="args" />
      </div>
    `
  })
}
