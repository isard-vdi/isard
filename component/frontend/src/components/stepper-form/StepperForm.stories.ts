import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { StepperForm } from './index'
import { ref } from 'vue'
import Button from '@/components/ui/button/Button.vue'

const steps = [
  {
    step: 1,
    title: 'Kind'
  },
  {
    step: 2,
    title: 'Settings'
  },
  {
    step: 3,
    title: 'Resources'
  },
  {
    step: 4,
    title: 'Desktops'
  }
]

const meta: Meta<typeof StepperForm> = {
  title: 'Stepper/StepperForm',
  component: StepperForm,
  tags: ['autodocs'],
  argTypes: {
    steps: {
      control: 'object',
      description:
        'Array of steps to display. Each step should have a `step` number, a `title` and an optional `description`.'
    },
    initialStep: {
      control: 'number',
      defaultValue: 1,
      description: 'Initial step to start with'
    }
  }
}

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    steps: steps,
    initialStep: 1
  },
  render: (args) => ({
    components: { StepperForm, Button },
    setup() {
      const currentStep = ref(args.initialStep)

      const handleStepChange = (step: number) => {
        currentStep.value = step
      }

      return { args, currentStep, handleStepChange }
    },
    template: `
      <div class="w-full max-w-4xl mx-auto p-6 flex">
        <StepperForm 
          :steps="args.steps" 
          :initial-step="args.initialStep"
          @step-change="handleStepChange"
        >
          <template #content="{ currentStep, canGoPrevious, canGoNext, handlePrevious, handleNext }">
            <div class="mt-8 p-6 border border-gray-warm-200 rounded-lg bg-base-white">
              <p class="text-base font-bold mb-2">Step {{ currentStep }} Content</p>
            </div>
            <div class="flex gap-2 mt-8 flex-row items-center ">
              <Button hierarchy="primary" @click="handlePrevious" :disabled="!canGoPrevious">
                Previous
              </Button>
              <Button hierarchy="primary" @click="handleNext">
                {{ canGoNext ? 'Next' : 'Complete' }}
              </Button>
            </div>
          </template>
        </StepperForm>
      </div>
    `
  })
}

export const StartingAtStep2: Story = {
  args: {
    steps: steps,
    initialStep: 2
  }
}

export const CustomSteps: Story = {
  args: {
    steps: [
      { step: 1, title: 'Personal Info', description: 'Enter your personal details' },
      { step: 2, title: 'Address', description: 'Enter your address details' },
      { step: 3, title: 'Payment', description: 'Enter your payment information' }
    ],
    initialStep: 1
  }
}
