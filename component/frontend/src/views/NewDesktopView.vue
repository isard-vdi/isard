<script setup lang="ts">
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import {
  createDesktopApiV4ItemDesktopPostMutation,
  checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions,
  checkStoragePoolCreationAvailabilityApiV4StoragePoolsCheckCreateAvailabilityGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertModal, QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import router from '@/router'
import { StepperForm, type StepperFormStep } from '@/components/stepper-form'
import Step1SelectTemplate from '@/components/new-desktop/Step1SelectTemplate.vue'
import Step2ConfigureDesktop from '@/components/new-desktop/Step2ConfigureDesktop.vue'
import Step3Creating from '@/components/new-desktop/Step3Creating.vue'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const { t } = useI18n()

// --------------------------------------------------
// Quota and storage checks
// --------------------------------------------------

const quotaQuery = useQuery({
  ...checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const storageQuery = useQuery({
  ...checkStoragePoolCreationAvailabilityApiV4StoragePoolsCheckCreateAvailabilityGetOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false,
  enabled: quotaQuery.isSuccess
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
const selectedTemplate = ref<{ id: string; image?: { url: string } } | null>(null)
const creationError = ref<string | null>(null)

const selectTemplate = (template: { id: string; image?: { url: string } }) => {
  selectedTemplate.value = selectedTemplate.value?.id === template.id ? null : template
}

const step2Ref = ref<InstanceType<typeof Step2ConfigureDesktop> | null>(null)

const nextButtonLabel = computed(() => {
  if (currentStep.value === 2) {
    return t('views.new-desktop.step-2.buttons.create-desktop.label')
  }
  return t('views.new-desktop.step-1.buttons.next.label')
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
  ...createDesktopApiV4ItemDesktopPostMutation(),
  onSuccess: (data) => {
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

const handleStep2Submit = (data: {
  name: string
  description: string
  desktopKind: string
  accessSettings: Record<string, unknown> | undefined
  hardwareSettings: Record<string, unknown> | undefined
}) => {
  creationError.value = null
  currentStep.value = 3

  submitDesktopCreate({
    body: {
      template_id: selectedTemplate.value!.id,
      name: data.name,
      description: data.description,
      persistent: data.desktopKind === 'persistent',
      guest_properties: {
        credentials: data.accessSettings?.credentials,
        fullscreen: data.accessSettings?.fullscreen,
        viewers: data.accessSettings?.viewers
      },
      hardware: {
        vcpus: data.hardwareSettings?.vcpus,
        memory: data.hardwareSettings?.memory,
        disk_bus: data.hardwareSettings?.diskBus,
        videos: [data.hardwareSettings?.videos],
        boot_order: [data.hardwareSettings?.bootOrder],
        interfaces: data.hardwareSettings?.interfaces,
        isos: data.hardwareSettings?.isos,
        floppies: data.hardwareSettings?.floppies
      },
      reservables: data.hardwareSettings?.reservables,
      bastion_target: data.accessSettings?.bastion
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
    :open="quotaQuery.isError.value"
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

  <template v-if="quotaCheckPassed">
    <!-- Header -->
    <header
      v-if="showStepsControls"
      class="flex flex-col md:flex-row items-start max-w-480 w-full mx-auto mb-8 gap-4"
    >
      <div class="flex flex-row items-center gap-4 w-full">
        <Button
          :as="RouterLink"
          :to="{ name: 'desktops' }"
          hierarchy="link-color"
          :icon="'arrow-left'"
          class="pb-6 pt-0 pl-0"
        >
          {{ t('views.new-desktop.header.cancel') }}
        </Button>
      </div>
      <div class="shrink-0 w-95">
        <StepperForm v-model="currentStep" :steps="steps" />
      </div>
      <div class="flex flex-row items-center justify-end gap-4 w-full">
        <Button hierarchy="link-color" :disabled="currentStep <= 1" @click="goToPreviousStep">
          {{ t('views.new-desktop.header.previous') }}
        </Button>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button class="min-w-32" :disabled="isNextButtonDisabled" @click="handleNextClick">
                {{ nextButtonLabel }}
              </Button>
            </TooltipTrigger>
            <TooltipContent
              v-if="!step2Ref?.areFormsValid && currentStep === 2"
              :title="$t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.title')"
              :subtitle="
                $t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.description')
              "
              side="top"
            />
          </Tooltip>
        </TooltipProvider>
      </div>
    </header>
    <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
      <!-- Content -->
      <div>
        <!-- Step 1 -->
        <div v-if="currentStep === 1">
          <Step1SelectTemplate
            @select-template="selectTemplate"
            :selected-id="selectedTemplate?.id ?? ''"
          />
        </div>
        <!-- Step 2 -->
        <div v-if="currentStep >= 2" v-show="currentStep === 2">
          <Alert v-if="creationError" variant="destructive" class="mb-6">
            <AlertTitle>{{ t(`api.new-desktop.errors.${creationError}.title`) }}</AlertTitle>
            <AlertDescription>{{
              t(`api.new-desktop.errors.${creationError}.description`)
            }}</AlertDescription>
          </Alert>
          <Step2ConfigureDesktop
            ref="step2Ref"
            :selected-template="selectedTemplate!"
            :on-go-back="goToPreviousStep"
            @submit="handleStep2Submit"
          />
        </div>
        <!-- Step 3 -->
        <div v-show="currentStep === 3">
          <Step3Creating />
        </div>
      </div>
    </main>
  </template>
</template>
