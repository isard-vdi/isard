<script setup lang="ts">
import { computed, watch } from 'vue'
import {
  Stepper,
  StepperItem,
  StepperTitle,
  StepperDescription,
  StepperIndicator,
  StepperSeparator,
  StepperTrigger
} from '@/components/ui/stepper'

export interface StepperFormStep {
  step: number
  title: string
  description?: string
  destructive?: boolean
}

interface Props {
  steps: StepperFormStep[]
  disableFutureSteps?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disableFutureSteps: true
})

const emit = defineEmits<{
  stepChange: [step: number]
  previous: [step: number]
  next: [step: number]
  complete: []
}>()

const currentStep = defineModel<number>({ default: 1 })

const canGoPrevious = computed(() => currentStep.value > 1)
const canGoNext = computed(() => currentStep.value < props.steps.length)

const handlePrevious = () => {
  if (canGoPrevious.value) {
    currentStep.value -= 1
    emit('previous', currentStep.value)
    emit('stepChange', currentStep.value)
  }
}

const handleNext = () => {
  if (canGoNext.value) {
    currentStep.value += 1
    emit('next', currentStep.value)
    emit('stepChange', currentStep.value)
  } else if (currentStep.value === props.steps.length) {
    emit('complete')
  }
}

// currentstep watch
watch(currentStep, (newStep) => {
  emit('stepChange', newStep)
})
</script>

<template>
  <div class="w-full">
    <Stepper v-model="currentStep">
      <StepperItem
        v-for="item in steps"
        :key="item.step"
        :step="item.step"
        :disabled="disableFutureSteps && item.step > currentStep"
        :class="item.step === steps[steps.length - 1].step ? '!flex-[0_0_auto]' : ''"
      >
        <div
          class="flex flex-col items-center gap-1.5"
          :class="item.step === steps[steps.length - 1].step ? 'w-auto' : 'w-full'"
        >
          <div
            class="flex items-center"
            :class="item.step === steps[steps.length - 1].step ? 'w-auto' : 'w-full'"
          >
            <div class="w-12 flex justify-center shrink-0">
              <StepperTrigger>
                <StepperIndicator :class="item.destructive ? 'ring-sm ring-error-200!' : ''">
                  {{ item.step }}
                </StepperIndicator>
              </StepperTrigger>
            </div>
            <div v-if="item.step !== steps[steps.length - 1].step" class="flex-1 min-w-0">
              <StepperSeparator />
            </div>
          </div>
          <div
            class="flex items-center mt-1"
            :class="item.step === steps[steps.length - 1].step ? 'w-auto' : 'w-full'"
          >
            <div class="w-12 flex items-center justify-center text-center shrink-0">
              <div class="flex flex-col items-center">
                <StepperTitle
                  class="text-sm font-bold whitespace-nowrap"
                  :class="item.destructive ? 'text-error-600!' : ''"
                >
                  {{ item.title }}
                </StepperTitle>
                <StepperDescription
                  v-if="item.description"
                  class="text-xs text-center mt-0.5 whitespace-nowrap"
                  :class="item.destructive ? 'text-error-600!' : ''"
                >
                  {{ item.description }}
                </StepperDescription>
              </div>
            </div>
          </div>
        </div>
      </StepperItem>
    </Stepper>

    <slot
      name="content"
      :current-step="currentStep"
      :can-go-previous="canGoPrevious"
      :can-go-next="canGoNext"
      :handle-previous="handlePrevious"
      :handle-next="handleNext"
    />
  </div>
</template>
