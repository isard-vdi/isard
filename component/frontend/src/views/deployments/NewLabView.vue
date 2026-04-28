<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/button/Button.vue'
import Icon from '@/components/icon/Icon.vue'
import LabFormSettings from '@/components/lab/LabFormSettings.vue'
import LabFormDesktops from '@/components/lab/LabFormDesktops.vue'
import UnsavedChangesModal from '@/components/modal/UnsavedChangesModal.vue'
import { createDeploymentMutation, getUserOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { MultiSelectTagItemType } from '@/components/multi-select'

import {
  Stepper,
  StepperItem,
  StepperTitle,
  StepperIndicator,
  StepperSeparator,
  StepperTrigger
} from '@/components/ui/stepper'

interface DesktopItem {
  id: number
  name: string
  description: string
  template: string | null
  hardware: Record<string, unknown>
  image: string
  guest_properties: Record<string, unknown>
  reservables: Record<string, unknown>
}

const { t } = useI18n()
const router = useRouter()

const isSubmitting = ref(false)
const submitError = ref(null)
const showUnsavedChangesModal = ref(false)
const pendingNavigation = ref<(() => void) | null>(null)

const currentStep = ref(1)
const steps = computed(() => [
  {
    step: 1,
    title: t('views.new-lab.step.kind')
  },
  {
    step: 2,
    title: t('views.new-lab.step.settings')
  },
  {
    step: 3,
    title: t('views.new-lab.step.desktops')
  }
])

const formData = ref({
  name: '',
  description: '',
  visibility: false,
  image: '',
  users: [] as MultiSelectTagItemType[],
  groups: [] as MultiSelectTagItemType[],
  desktops: [] as DesktopItem[],
  selectedKind: ''
})

const hasChanges = computed(() => {
  return (
    formData.value.name !== '' ||
    formData.value.description !== '' ||
    formData.value.visibility !== false ||
    formData.value.image !== '' ||
    formData.value.users.length > 0 ||
    formData.value.groups.length > 0 ||
    formData.value.desktops.length > 0
  )
})

const isStep1Valid = computed(() => {
  return formData.value.selectedKind === 'from-scratch'
})

const isStep2Valid = computed(() => {
  return (
    formData.value.name.trim() !== '' &&
    (formData.value.users.length > 0 || formData.value.groups.length > 0)
  )
})

const isStep3Valid = computed(() => {
  return (
    formData.value.desktops.length > 0 &&
    formData.value.desktops.every(
      (desktop) => desktop.name.trim() !== '' && desktop.template !== null
    )
  )
})

const canProceedToNextStep = computed(() => {
  switch (currentStep.value) {
    case 1:
      return isStep1Valid.value
    case 2:
      return isStep2Valid.value
    case 3:
      return isStep3Valid.value
    default:
      return false
  }
})

const getNextButtonTooltip = computed(() => {
  if (canProceedToNextStep.value) return ''

  switch (currentStep.value) {
    case 1:
      return !formData.value.selectedKind ? t('views.form-lab.tooltip.select-kind') : ''
    case 2:
      if (!formData.value.name.trim()) {
        return t('views.form-lab.tooltip.enter-name')
      }
      if (formData.value.users.length === 0 && formData.value.groups.length === 0) {
        return t('views.form-lab.tooltip.select-users-or-groups')
      }
      return ''
    case 3:
      if (formData.value.desktops.length === 0) {
        return t('views.form-lab.tooltip.add-desktop')
      }
      if (formData.value.desktops.some((d) => !d.name.trim())) {
        return t('views.form-lab.tooltip.desktop-name-required')
      }
      return ''
    default:
      return ''
  }
})

const canAddNewDesktop = computed(() => {
  return formData.value.desktops.every((desktop) => desktop.template !== null)
})

const { data: currentUser } = useQuery(getUserOptions())
const createDeploymentMut = useMutation(createDeploymentMutation())

const transformFormDataToApiFormat = (data: {
  name: string
  description: string
  visibility: boolean
  image: string
  users: MultiSelectTagItemType[]
  groups: MultiSelectTagItemType[]
  desktops: DesktopItem[]
}) => {
  const userIds = data.users.map((user: MultiSelectTagItemType) => user.id)
  const groupIds = data.groups.map((group: MultiSelectTagItemType) => group.id)
  const createDict = data.desktops.map((desktop: DesktopItem) => {
    const apiHardware = {
      ...desktop.hardware,
      vcpus: desktop.hardware.cpu || desktop.hardware.vcpus,
      memory: desktop.hardware.ram || desktop.hardware.memory,
      boot_order: desktop.hardware.boot
        ? [desktop.hardware.boot]
        : desktop.hardware.boot_order || ['disk'],
      interfaces: desktop.hardware.networkInterfaces || desktop.hardware.interfaces || [],
      disk_bus: desktop.hardware.disk_bus || 'virtio',
      floppies: desktop.hardware.floppies || [],
      isos: desktop.hardware.isos || []
    }

    return {
      name: desktop.name,
      template: desktop.template,
      description: desktop.description || '',
      guest_properties: desktop.guest_properties,
      image: desktop.image,
      hardware: apiHardware,
      reservables: desktop.reservables
    }
  })

  return {
    name: data.name,
    description: data.description || '',
    kind: 'lab' as const,
    tag_visible: data.visibility,
    allowed: {
      users: userIds.length > 0 ? userIds : false,
      groups: groupIds.length > 0 ? groupIds : false,
      categories: false,
      roles: false
    },
    co_owners: [],
    resources: [],
    create_dict: createDict,
    image: {
      id: '',
      type: '',
      url: ''
    },
    user: currentUser.value?.id || '',
    user_permissions: []
  }
}

const handleFormSubmit = async () => {
  try {
    isSubmitting.value = true
    submitError.value = null

    const apiData = transformFormDataToApiFormat(formData.value)
    await createDeploymentMut.mutateAsync({
      body: apiData
    })

    router.push('/labs')
  } catch (error: unknown) {
    submitError.value =
      error instanceof Error ? error.message : 'An error occurred while creating the lab.'
  } finally {
    isSubmitting.value = false
  }
}

const goToPreviousStep = () => {
  if (currentStep.value > 1) {
    currentStep.value--
  }
}

const goToNextStep = () => {
  if (currentStep.value < steps.value.length && canProceedToNextStep.value) {
    currentStep.value++
  }
}

const handleNextOrSubmit = () => {
  if (currentStep.value >= steps.value.length) {
    if (isStep3Valid.value) {
      handleFormSubmit()
    }
  } else {
    goToNextStep()
  }
}

const selectKind = (kind: string) => {
  formData.value.selectedKind = kind
  if (kind === 'from-scratch') {
    goToNextStep()
  }
}

const handleGoBack = () => {
  if (hasChanges.value) {
    pendingNavigation.value = () => router.push('/labs')
    showUnsavedChangesModal.value = true
  } else {
    router.push('/labs')
  }
}

const confirmDiscardChanges = () => {
  showUnsavedChangesModal.value = false
  if (pendingNavigation.value) {
    pendingNavigation.value()
    pendingNavigation.value = null
  }
}

const cancelDiscardChanges = () => {
  showUnsavedChangesModal.value = false
  pendingNavigation.value = null
}

let desktopIdCounter = 0

const addDesktop = () => {
  if (!canAddNewDesktop.value) return

  const newDesktop: DesktopItem = {
    id: ++desktopIdCounter,
    name: '',
    description: '',
    template: null,
    hardware: {},
    image: '',
    guest_properties: {},
    reservables: {}
  }
  formData.value.desktops.push(newDesktop)
}

const updateDesktop = (id: number, key: string, value: unknown) => {
  const index = formData.value.desktops.findIndex((d) => d.id === id)
  if (index !== -1) {
    formData.value.desktops[index] = {
      ...formData.value.desktops[index],
      [key]: value
    }
  }
}

const deleteDesktop = (id: number) => {
  formData.value.desktops = formData.value.desktops.filter((d) => d.id !== id)
}

window.addEventListener('beforeunload', (e) => {
  if (hasChanges.value) {
    e.preventDefault()
    e.returnValue = ''
  }
})
</script>

<template>
  <div class="flex flex-col w-full items-center gap-24">
    <div class="w-full flex items-center justify-between gap-4">
      <div class="flex-1 flex justify-center">
        <Stepper v-model="currentStep" orientation="horizontal" class="max-w-192">
          <StepperItem
            v-for="item in steps"
            :key="item.step"
            :step="item.step"
            :class="{
              'flex-1': item.step !== steps[steps.length - 1].step,
              'flex-2': item.step === steps[steps.length - 1].step
            }"
          >
            <StepperTrigger :disabled="item.step > currentStep && item.step > 1">
              <StepperIndicator>
                {{ item.step }}
              </StepperIndicator>
              <div class="flex flex-col items-center w-full">
                <StepperTitle>
                  {{ item.title }}
                </StepperTitle>
              </div>
            </StepperTrigger>
            <StepperSeparator v-if="item.step !== steps[steps.length - 1].step" />
          </StepperItem>
        </Stepper>
      </div>
      <div class="flex gap-2 absolute right-12 mt-40 lg:mt-auto">
        <Button
          v-show="currentStep > 1"
          hierarchy="link-color"
          :disabled="currentStep <= 1"
          @click="goToPreviousStep"
        >
          {{ t('components.stepper.navigation.previous') }}
        </Button>
        <Button
          hierarchy="primary"
          :disabled="isSubmitting || !canProceedToNextStep"
          :loading="isSubmitting"
          :title="getNextButtonTooltip"
          @click="handleNextOrSubmit"
        >
          {{
            currentStep >= steps.length
              ? t('views.new-lab.submit')
              : t('components.stepper.navigation.next')
          }}
        </Button>
      </div>
    </div>

    <div class="flex flex-col gap-16 max-w-320">
      <!-- Step 1: Kind Selection -->
      <div v-show="currentStep === 1" id="kind-step" class="step">
        <div class="flex flex-col p-6 w-288">
          <h1 class="text-lg font-semibold mb-6 text-gray-warm-900">
            {{ t('views.new-lab.header.choose') }}
          </h1>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div
              class="cursor-pointer flex flex-col gap-2 p-6 border border-gray-warm-300 rounded-xl bg-white hover:shadow-sm transition"
              @click="selectKind('from-scratch')"
            >
              <div
                class="w-10 h-10 rounded-full bg-secondary-4-500 border-4 border-secondary-4-400 flex items-center justify-center"
              >
                <Icon name="plus" />
              </div>
              <h2 class="font-semibold text-gray-warm-800">
                {{ t('views.new-lab.from-scratch.title') }}
              </h2>
              <p class="text-sm text-gray-warm-600">
                {{ t('views.new-lab.from-scratch.description') }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 2: Settings -->
      <div v-show="currentStep === 2" id="settings-step" class="step">
        <LabFormSettings
          :name="formData.name"
          :description="formData.description"
          :visibility="formData.visibility"
          :image="formData.image"
          :selected-users="formData.users"
          :selected-groups="formData.groups"
          @update:name="formData.name = $event"
          @update:description="formData.description = $event"
          @update:visibility="formData.visibility = $event"
          @update:image="formData.image = $event"
          @update:selected-users="formData.users = $event"
          @update:selected-groups="formData.groups = $event"
        />
      </div>

      <!-- Step 3: Desktops -->
      <div v-show="currentStep === 3" id="desktops-step" class="step w-full">
        <LabFormDesktops
          :desktops="formData.desktops"
          @add-desktop="addDesktop"
          @update-desktop="updateDesktop"
          @delete-desktop="deleteDesktop"
        />
      </div>

      <div
        v-if="submitError"
        class="text-error-600 mb-4 p-2 bg-error-50 border border-error-200 rounded"
      >
        {{ submitError }}
      </div>
    </div>

    <UnsavedChangesModal
      :open="showUnsavedChangesModal"
      @confirm="confirmDiscardChanges"
      @cancel="cancelDiscardChanges"
    />
  </div>
</template>
