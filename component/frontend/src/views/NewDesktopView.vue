<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import {
  createDesktopMutation,
  checkQuotaNewDesktopOptions,
  checkQuotaNewVolatileDesktopOptions,
  checkStoragePoolCreationAvailabilityOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import {
  toBastionTarget,
  toDomainHardware,
  toGuestProperties,
  toImageInput,
  toReservables
} from '@/lib/domainPayload'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertModal, QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { useUserStore } from '@/stores/user'
import router from '@/router'
import { StepperForm, type StepperFormStep } from '@/components/stepper-form'
import Step1SelectTemplate from '@/components/new-desktop/Step1SelectTemplate.vue'
import Step2ConfigureDesktop from '@/components/new-desktop/Step2ConfigureDesktop.vue'
import type { DomainConfigurationPanelData } from '@/components/domain/DomainConfigurationPanel.vue'
import Step3Creating from '@/components/new-desktop/Step3Creating.vue'
import { FormHeader } from '@/components/form-header'

import { cn } from '@/lib/utils'
import { newDesktopErrorKey } from '@/lib/api-errors'

const { t, te } = useI18n()

// --------------------------------------------------
// Quota and storage checks
// --------------------------------------------------

const userStore = useUserStore()
const temporalAvailable = computed(() => userStore.config?.show_temporal_tab !== false)

// Temporal desktops count against the volatile quota, so a full desktops quota
// must not close the wizard on its own.
const quotaQuery = useQuery({
  ...checkQuotaNewDesktopOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const volatileQuotaQuery = useQuery({
  ...checkQuotaNewVolatileDesktopOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false,
  enabled: temporalAvailable
})

const anyQuotaLeft = computed(
  () => quotaQuery.isSuccess.value || volatileQuotaQuery.isSuccess.value
)
const noQuotaLeft = computed(
  () => quotaQuery.isError.value && (!temporalAvailable.value || volatileQuotaQuery.isError.value)
)

const storageQuery = useQuery({
  ...checkStoragePoolCreationAvailabilityOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false,
  enabled: anyQuotaLeft
})

const quotaCheckPassed = computed(() => storageQuery.isSuccess.value)

// --------------------------------------------------

const currentStep = ref(1)
const showStepsControls = computed(() => {
  return currentStep.value <= 2
})
const goToPreviousStep = () => {
  if (currentStep.value > 1) {
    if (currentStep.value === 2) {
      selectedTemplate.value = null
    }
    currentStep.value--
  } else {
    router.push({ name: 'desktops' })
  }
}

// Step 1: Select Template
const selectedTemplate = ref<{ id: string; image?: DomainImageOutput } | null>(null)
const creationError = ref<string | null>(null)
const creationErrorKey = computed(() => newDesktopErrorKey(creationError.value, { t, te }))

const selectTemplate = (template: { id: string; image?: DomainImageOutput }) => {
  selectedTemplate.value = selectedTemplate.value?.id === template.id ? null : template
}

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)
const step2Ref = ref<InstanceType<typeof Step2ConfigureDesktop> | null>(null)

const nextButtonLabel = computed(() => {
  if (currentStep.value === 2) {
    return t('views.new-desktop.step-2.buttons.create-desktop.label')
  }
  return t('views.new-desktop.step-1.buttons.next.label')
})

const nextButtonTooltip = computed(() => {
  if (currentStep.value !== 2 || step2Ref.value?.areFormsValid) return undefined
  return {
    title: t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.title'),
    description: t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.description')
  }
})

const isNextButtonDisabled = computed(() => {
  if (currentStep.value === 1) {
    return !selectedTemplate.value?.id
  }
  if (currentStep.value === 2) {
    return !step2Ref.value?.areFormsValid
  }
  return true
})

const handleNextClick = () => {
  if (currentStep.value === 1) {
    if (!selectedTemplate.value?.id) return
    creationError.value = null
    currentStep.value = 2
  } else if (currentStep.value === 2) {
    step2Ref.value?.handleSubmit()
  }
}

// Step 2: Configure Desktop & Submit
const {
  mutate: submitDesktopCreate,
  isPending: submitDesktopCreateIsPending,
  isError: submitDesktopCreateIsError,
  error: submitDesktopCreateError
} = useMutation({
  ...createDesktopMutation(),
  onSuccess: (data) => {
    formHeaderRef.value?.allowLeave()
    router.push({
      name: 'single-desktop',
      params: {
        desktopId: data.id,
        action: 'desktop-created'
      }
    })
  },
  onError: (error) => {
    creationError.value = 'description_code' in error ? error.description_code : 'generic'
    currentStep.value = 2
  }
})

const handleStep2Submit = (data: DomainConfigurationPanelData) => {
  creationError.value = null
  currentStep.value = 3

  submitDesktopCreate({
    body: {
      template_id: selectedTemplate.value!.id,
      name: data.name,
      description: data.description,
      persistent: data.kind === 'persistent',
      guest_properties: toGuestProperties(data.access),
      hardware: toDomainHardware(data.hardware),
      reservables: toReservables(data.hardware),
      image: toImageInput(data.image),
      bastion_target: toBastionTarget(data.access?.bastion)
    }
  })
}

const steps = computed<StepperFormStep[]>(() => {
  return [
    {
      step: 1,
      title: t(`views.new-desktop.step-1.title`)
    },
    {
      step: 2,
      title: t(`views.new-desktop.step-2.title`)
    }
  ]
})
</script>
<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="noQuotaLeft"
    :title="t('components.desktops.quota-exceeded-modal.title')"
    :description="t('components.desktops.quota-exceeded-modal.description')"
    :cancel-label="t('components.desktops.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'desktops' }"
  />

  <!-- Storage Unavailable Modal -->
  <AlertModal
    :open="storageQuery.isError.value"
    level="danger"
    size="md"
    :title="t('components.desktops.storage-unavailable-modal.title')"
    :description="t('components.desktops.storage-unavailable-modal.description')"
    :close-on-backdrop-click="false"
    :show-close-button="false"
  >
    <template #footer>
      <Button hierarchy="primary" @click="router.push({ name: 'desktops' })">{{
        t('components.desktops.storage-unavailable-modal.go-to-desktops')
      }}</Button>
    </template>
  </AlertModal>

  <div v-if="quotaCheckPassed" class="h-full flex flex-col">
    <!-- Header -->
    <FormHeader
      v-if="showStepsControls"
      ref="formHeaderRef"
      :cancel-to="{ name: 'desktops' }"
      :confirm-cancel="!!step2Ref?.isDirty"
      :show-previous="currentStep > 1"
      :next-label="nextButtonLabel"
      :next-disabled="isNextButtonDisabled"
      :next-tooltip="nextButtonTooltip"
      @previous="goToPreviousStep"
      @next="handleNextClick"
    >
      <template #stepper>
        <div class="shrink-0 w-80">
          <StepperForm v-model="currentStep" :steps="steps" />
        </div>
      </template>
    </FormHeader>
    <main
      :class="cn(currentStep !== 2 ? 'max-w-320' : undefined)"
      class="w-full mx-auto flex flex-1 flex-col gap-6"
    >
      <!-- Content -->
      <div class="flex flex-1 flex-col">
        <!-- Step 1 -->
        <div v-if="currentStep === 1">
          <Step1SelectTemplate
            :selected-id="selectedTemplate?.id ?? ''"
            @select-template="selectTemplate"
          />
        </div>
        <!-- Step 2 -->
        <div v-if="currentStep >= 2" v-show="currentStep === 2" class="max-w-320 m-auto">
          <Alert v-if="creationError" variant="destructive" class="mb-6">
            <AlertTitle>{{ t(`api.new-desktop.errors.${creationErrorKey}.title`) }}</AlertTitle>
            <AlertDescription>{{
              t(`api.new-desktop.errors.${creationErrorKey}.description`)
            }}</AlertDescription>
          </Alert>
          <!-- Keyed: the step stays mounted across steps and its template queries
               are built once, so a new template needs a new instance. -->
          <Step2ConfigureDesktop
            ref="step2Ref"
            :key="selectedTemplate?.id"
            :selected-template="selectedTemplate!"
            :persistent-quota-exceeded="quotaQuery.isError.value"
            :temporal-quota-exceeded="volatileQuotaQuery.isError.value"
            @submit="handleStep2Submit"
          />
        </div>
        <!-- Step 3 -->
        <div v-show="currentStep === 3">
          <Step3Creating />
        </div>
      </div>
    </main>
  </div>
</template>
