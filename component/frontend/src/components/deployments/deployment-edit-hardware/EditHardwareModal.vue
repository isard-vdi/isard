<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CreateDesktopRequest } from '@/gen/oas/apiv4'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/modal'
import { Separator } from '@/components/ui/separator'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { selectedViewerKeys } from '@/lib/viewers'

const { t, d } = useI18n()

interface Props {
  open?: boolean
  data: CreateDesktopRequest
  restrictedFieldsDetails?: { name: string; oldValue: any; newValue: any }[]
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
  submit: [
    {
      accessSettings: any
      hardwareSettings: any
    }
  ]
}>()

const showAccessCustomization = ref(false)
const showHardwareCustomization = ref(false)

const desktopData = ref<CreateDesktopRequest>(props.data)

const submitButtonLoading = ref(false)
const handleSubmit = () => {
  submitButtonLoading.value = true

  const accessSettings = accessFormRef.value?.getFormData()
  const hardwareSettings = hardwareFormRef.value?.getFormData()

  emit('submit', {
    accessSettings,
    hardwareSettings
  })

  submitButtonLoading.value = false
}

const accessFormRef = ref<{
  getFormData: () => any
  isValid: boolean
  removedViewerLabels: string[]
} | null>(null)
const hardwareFormRef = ref<{
  getFormData: () => any
  isValid: boolean
  limitedFields: any
  addInterface: (ifaceId: string) => void
  removeInterface: (ifaceId: string) => void
  interfaces: string[]
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

const selectedViewers = computed<string[]>(() =>
  selectedViewerKeys(desktopData.value.guest_properties?.viewers)
)

const removedViewerLabels = computed<string[]>(() => accessFormRef.value?.removedViewerLabels ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  hardwareFormRef.value?.addInterface(ifaceId)
}

// Check if hardware form has limited fields (using data from DomainHardwareForm)
const hasLimitedFields = computed(() => {
  const limitedFields = hardwareFormRef.value?.limitedFields
  return !!(
    limitedFields &&
    limitedFields !== null &&
    typeof limitedFields === 'object' &&
    Object.keys(limitedFields).length > 0
  )
})
</script>

<template>
  <Modal
    :open="props.open"
    size="7xl"
    _class="h-full"
    :title="
      t('components.deployments.form-update-hardware-modal.title', {
        'desktop-name': desktopData.name
      })
    "
    :description="
      t('components.deployments.form-update-hardware-modal.description', {
        'desktop-name': desktopData.name
      })
    "
    @close="emit('close')"
  >
    <template #default>
      <div class="flex flex-col gap-8 mb-8 px-8 py-4">
        <div class="flex flex-col gap-6">
          <div>
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.access.title') }}
            </h1>
            <h2 class="text-sm font-regular">
              {{ t('views.new-desktop.step-2.access.description') }}
            </h2>
          </div>

          <DomainAccessSummary
            :credentials="desktopData.guest_properties?.credentials"
            :viewers="selectedViewers"
            :fullscreen="desktopData.guest_properties?.fullscreen"
          />

          <Alert
            v-if="removedViewerLabels.length && !showAccessCustomization"
            variant="default"
            class="border-error-600"
          >
            <FeaturedIconOutline kind="outline" color="error" />
            <AlertTitle>{{ t('components.domain.access.viewers-removed.title') }}</AlertTitle>
            <AlertDescription>
              {{ t('components.domain.access.viewers-removed.description') }}
              <ul class="mt-3 space-y-1">
                <li
                  v-for="label in removedViewerLabels"
                  :key="label"
                  class="text-sm font-semibold text-error-600"
                >
                  {{ label }}
                </li>
              </ul>
            </AlertDescription>
          </Alert>

          <div class="flex items-center gap-2">
            <Separator />
            <Button
              hierarchy="secondary-gray"
              size="sm"
              :icon="showAccessCustomization ? 'chevron-up' : 'chevron-down'"
              @click="showAccessCustomization = !showAccessCustomization"
              >{{
                t(
                  `views.new-desktop.step-2.access.${showAccessCustomization ? 'hide' : 'show'}-access-customization`
                )
              }}</Button
            >
            <Separator />
          </div>
          <div v-show="showAccessCustomization">
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.all-hardware.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-desktop.step-2.all-hardware.description') }}
            </p>
            <DomainAccessForm
              ref="accessFormRef"
              :show-bastion-config="false"
              :credentials="desktopData.guest_properties?.credentials"
              :fullscreen="desktopData.guest_properties?.fullscreen"
              :viewers="selectedViewers"
              :hardware-interfaces="hardwareInterfaces"
              :on-request-add-interface="handleAddInterfaceFromAccessForm"
            />
          </div>
        </div>

        <div class="flex flex-col gap-6">
          <div>
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.hardware-summary.title') }}
            </h1>
            <h2 class="text-sm font-regular">
              {{ t('views.new-desktop.step-2.hardware-summary.description') }}
            </h2>
          </div>

          <!-- Informational alert for limited hardware fields -->
          <Alert v-if="hasLimitedFields" variant="default" class="mb-6 border-error-600">
            <FeaturedIconOutline kind="outline" color="error" />
            <AlertTitle>{{ t('views.new-desktop.step-2.hardware-limited.title') }}</AlertTitle>
            <AlertDescription>
              {{ t('views.new-desktop.step-2.hardware-limited.description') }}
              <ul v-if="props.restrictedFieldsDetails?.length" class="mt-3 space-y-2">
                <li
                  v-for="field in props.restrictedFieldsDetails"
                  :key="field.name"
                  class="text-sm"
                >
                  <span class="font-semibold text-error-600">{{ field.name }}: </span>
                  <span class="text-error-600">{{ field.oldValue }} → {{ field.newValue }}</span>
                </li>
              </ul>
            </AlertDescription>
          </Alert>

          <DomainHardwareSummary
            :vcpu="desktopData.hardware?.vcpus"
            :memory="desktopData.hardware?.memory"
            :disk-bus="desktopData.hardware?.disk_bus"
            :videos="desktopData.hardware?.videos"
            :interfaces="desktopData.hardware?.interfaces"
            :boot-order="desktopData.hardware?.boot_order"
            :isos="desktopData.hardware?.isos"
            :floppies="desktopData.hardware?.floppies"
            :loading="false"
            :reservables="desktopData.reservables?.vgpus"
          />

          <div class="flex items-center gap-2">
            <Separator />
            <Button
              hierarchy="secondary-gray"
              size="sm"
              :icon="showHardwareCustomization ? 'chevron-up' : 'chevron-down'"
              @click="showHardwareCustomization = !showHardwareCustomization"
            >
              {{
                t(
                  `views.new-desktop.step-2.hardware-summary.${showHardwareCustomization ? 'hide' : 'show'}-hardware-customization`
                )
              }}
            </Button>
            <Separator />
          </div>
          <div v-show="showHardwareCustomization">
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.all-hardware.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-desktop.step-2.all-hardware.description') }}
            </p>
            <DomainHardwareForm
              ref="hardwareFormRef"
              _template-id="props.data?.template_id"
              :vcpus="desktopData.hardware?.vcpus"
              :memory="desktopData.hardware?.memory"
              :disk-bus="desktopData.hardware?.disk_bus"
              :videos="desktopData.hardware?.videos"
              :interfaces="desktopData.hardware?.interfaces"
              :boot-order="desktopData.hardware?.boot_order"
              :isos="desktopData.hardware?.isos"
              :floppies="desktopData.hardware?.floppies"
              :reservables="desktopData.reservables"
              :limited-hardware="desktopData.limited_hardware"
            />
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.deployments.form-update-hardware-modal.cancel') }}
      </Button>
      <Button
        hierarchy="primary"
        :disabled="submitButtonLoading"
        :icon="submitButtonLoading ? 'loading-02' : undefined"
        icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
        @click="
          () => {
            handleSubmit()
          }
        "
      >
        {{ t('components.deployments.form-update-hardware-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
