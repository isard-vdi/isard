<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { useUserStore } from '@/stores/user'
import { getTemplateDetailsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import { CheckboxGroup } from '@/components/checkbox-group'
import { DesktopCardBase } from '@/components/desktop-card'
import { DesktopCardHeader } from '@/components/desktop-card'
import { useDomainInfoForm } from '@/composables/useDomainInfoForm'
import { DesktopCardSkeleton } from '@/components/desktop-card'
import { FieldError } from '@/components/ui/field'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'

const { t } = useI18n()
const userStore = useUserStore()

interface Template {
  id: string
  image?: { url: string }
}

const props = defineProps<{
  selectedTemplate: Template
  onGoBack: () => void
}>()

const emit = defineEmits<{
  submit: [
    data: {
      name: string
      description: string
      desktopKind: string
      accessSettings: Record<string, unknown> | undefined
      hardwareSettings: Record<string, unknown> | undefined
    }
  ]
}>()

// Fetch selected template info when selectedTemplate changes (used for hardware summary)
const {
  isPending: templateLoading,
  error: templateError,
  data: templateData
} = useQuery({
  ...getTemplateDetailsOptions({
    path: {
      template_id: props.selectedTemplate?.id || ''
    }
  }),
  enabled: computed(() => props.selectedTemplate !== null)
})

// Hardware summary computed properties
const hardwareSummaryBootOrder = computed(() => {
  return templateData.value?.boot_order.map((bo) => bo.name) || []
})
const hardwareSummaryIsos = computed(() => {
  return templateData.value?.isos?.map((iso) => iso.name) || []
})
const hardwareSummaryFloppies = computed(() => {
  const data = templateData.value as { floppies?: { name: string }[] } | undefined
  return (data?.floppies || []).map((floppy) => floppy.name)
})
const hardwareSummaryDiskBus = computed(() => {
  return templateData.value?.disk_bus || ''
})
const hardwareSummaryVideos = computed(() => {
  return templateData.value?.videos.map((video) => video.name) || []
})
const hardwareSummaryInterfaces = computed(() => {
  return templateData.value?.interfaces.map((network) => network.name) || []
})
const hardwareSummaryVgpus = computed(() => {
  return templateData.value?.reservables?.vgpus || []
})

const accessFormRef = ref<{ getFormData: () => Record<string, unknown>; isValid: boolean } | null>(
  null
)
const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  limitedFields: Record<string, unknown> | null
  getInterfaces: () => string[]
  addInterface: (ifaceId: string) => void
  removeInterface: (ifaceId: string) => void
  interfaces: string[]
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  hardwareFormRef.value?.addInterface(ifaceId)
}
const hardwareFormIsValid = computed(() => {
  return hardwareFormRef.value?.isValid ?? true
})
const showAccessCustomization = ref(false)
const showHardwareCustomization = ref(false)
const desktopKind = ref<'persistent' | 'nonpersistent'>('persistent')

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

// Format value for display (helper function)
const formatValue = (value: unknown) => {
  if (Array.isArray(value)) {
    return value.map((v: Record<string, unknown>) => v.name || v.id || v).join(', ') || 'None'
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    return obj.name || obj.id || value || 'None'
  }
  return value || 'None'
}

// Get list of restricted fields with their restrictions for display
const restrictedFieldsDetails = computed(() => {
  const limitedFields = hardwareFormRef.value?.limitedFields
  if (!limitedFields || typeof limitedFields !== 'object') return []

  const fieldNameMap: Record<string, string> = {
    vcpus: t('components.domain.hardware.vcpus.label'),
    memory: t('components.domain.hardware.memory.label'),
    disk_bus: t('components.domain.hardware.disk-bus.label'),
    videos: t('components.domain.hardware.videos.label'),
    boot_order: t('components.domain.hardware.boots.label'),
    isos: t('components.domain.hardware.isos.label'),
    floppies: t('components.domain.hardware.floppies.label'),
    vgpus: t('components.domain.hardware.vgpus.label'),
    interfaces: t('components.domain.hardware.networks.label')
  }

  return Object.entries(limitedFields).map(
    ([key, value]: [string, { old_value: unknown; new_value: unknown }]) => ({
      name: fieldNameMap[key] || key,
      oldValue: formatValue(value.old_value),
      newValue: formatValue(value.new_value)
    })
  )
})

// Desktop inherited info form (description seeded from template)
const desktopInfoForm = useDomainInfoForm({
  description: () => templateData.value?.description
})

const infoFormValues = desktopInfoForm.useStore((state) => state.values)

const desktopKindOptions = computed(() => {
  const showTemporalTab = userStore.config?.show_temporal_tab ?? true

  const options = [
    {
      color: 'persistent',
      title: t('views.new-desktop.step-2.desktop-kind.persistent.title'),
      description: t('views.new-desktop.step-2.desktop-kind.persistent.description'),
      value: 'persistent'
    }
  ]

  if (showTemporalTab) {
    options.push({
      color: 'temporary',
      title: t('views.new-desktop.step-2.desktop-kind.nonpersistent.title'),
      description: t('views.new-desktop.step-2.desktop-kind.nonpersistent.description'),
      value: 'nonpersistent'
    })
  }

  return options
})

const infoValid = desktopInfoForm.useStore((state) => state.isValid)
const infoIsTouched = desktopInfoForm.useStore((state) => !state.isPristine)

const areFormsValid = computed(() => {
  return (
    infoIsTouched.value &&
    infoValid.value &&
    (hardwareFormIsValid.value ?? true) &&
    (accessFormRef.value?.isValid ?? true)
  )
})

const toggleAccessCustomization = () => {
  showAccessCustomization.value = !showAccessCustomization.value
}

const toggleHardwareCustomization = () => {
  showHardwareCustomization.value = !showHardwareCustomization.value
}

const handleSubmit = () => {
  if (!areFormsValid.value) {
    return
  }

  const desktopName = desktopInfoForm.getFieldValue('name')
  const desktopDescription = desktopInfoForm.getFieldValue('description')
  const accessSettings = accessFormRef.value?.getFormData()
  const hardwareSettings = hardwareFormRef.value?.getFormData()

  emit('submit', {
    name: desktopName,
    description: desktopDescription,
    desktopKind: desktopKind.value,
    accessSettings,
    hardwareSettings
  })
}

defineExpose({
  handleSubmit,
  areFormsValid
})
</script>

<template>
  <div>
    <div class="flex gap-6">
      <template v-if="templateLoading">
        <div class="flex flex-col gap-2">
          <DesktopCardSkeleton class="w-[426px] h-[310px]" />
        </div>
      </template>
      <div v-else class="flex-1">
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.new-desktop.step-2.preview.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.new-desktop.step-2.preview.description') }}
        </p>
        <!-- TODO: Allow adding an image -->
        <DesktopCardBase
          :image-url="selectedTemplate?.image?.url || ''"
          :desktop-kind="desktopKind"
        >
          <template #header>
            <DesktopCardHeader
              :name="infoFormValues.name"
              :description="infoFormValues.description"
            />
          </template>
          <template #footer>
            <Button
              icon="play"
              icon-class="fill-current"
              hierarchy="secondary-color"
              size="sm"
              class="shrink-0"
              disabled
            >
              {{ t('components.desktops.desktop-card.status.stopped.action') }}
            </Button>
          </template>
        </DesktopCardBase>
      </div>
      <div class="flex-1">
        <div class="mb-6">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-desktop.step-2.desktop-information.title') }}
          </h3>
          <p class="text-sm font-regular mb-6">
            {{ t('views.new-desktop.step-2.desktop-information.description') }}
          </p>
          <div class="flex flex-col gap-3">
            <div class="flex flex-col gap-1">
              <desktopInfoForm.Field v-slot="{ field }" name="name">
                <InputField
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  :placeholder="t('components.domain.info.name.placeholder')"
                  maxlength="50"
                  autofocus
                  @update:model-value="(value) => field.handleChange(String(value))"
                  @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
                  @blur="field.handleBlur"
                />
              </desktopInfoForm.Field>
            </div>

            <desktopInfoForm.Field v-slot="{ field }" name="description">
              <Textarea
                :model-value="field.state.value"
                maxlength="255"
                class="bg-base-white resize-none"
                :placeholder="t('components.domain.info.description.placeholder')"
                @update:model-value="(value) => field.handleChange(String(value))"
              />
            </desktopInfoForm.Field>
          </div>
        </div>
        <div>
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-desktop.step-2.desktop-kind.title') }}
          </h3>
          <p class="text-sm font-regular mb-6">
            {{ t('views.new-desktop.step-2.desktop-kind.description') }}
          </p>
          <CheckboxGroup
            v-model="desktopKind"
            :items="desktopKindOptions"
            kind="featured-icon"
            type="single"
            check-type="radio"
          />
        </div>
      </div>
    </div>
    <div class="mt-8">
      <h3 class="text-lg font-semibold text-gray-warm-900">
        {{ t('views.new-desktop.step-2.access.title') }}
      </h3>
      <p class="text-sm font-regular mb-6">
        {{ t('views.new-desktop.step-2.access.description') }}
      </p>
      <DomainAccessSummary
        :credentials="templateData?.credentials"
        :viewers="templateData?.viewers"
        :fullscreen="templateData?.fullscreen"
      />
      <Separator orientation="horizontal" class="my-8">
        <template #default>
          <Button
            hierarchy="secondary-gray"
            size="sm"
            :icon="showAccessCustomization ? 'chevron-up' : 'chevron-down'"
            @click="toggleAccessCustomization"
          >
            {{
              t(
                `views.new-desktop.step-2.access.${showAccessCustomization ? 'hide' : 'show'}-access-customization`
              )
            }}
          </Button>
        </template>
      </Separator>
      <div v-show="showAccessCustomization" class="my-8">
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.new-desktop.step-2.all-access.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.new-desktop.step-2.all-access.description') }}
        </p>
        <DomainAccessForm
          ref="accessFormRef"
          :template-id="selectedTemplate?.id"
          :show-bastion-config="false"
          :hardware-interfaces="hardwareInterfaces"
          :on-request-add-interface="handleAddInterfaceFromAccessForm"
        />
      </div>
    </div>
    <div class="my-8">
      <h3 class="text-lg font-semibold text-gray-warm-900">
        {{ t('views.new-desktop.step-2.hardware-summary.title') }}
      </h3>
      <p class="text-sm font-regular mb-6">
        {{ t('views.new-desktop.step-2.hardware-summary.description') }}
      </p>

      <!-- Informational alert for limited hardware fields -->
      <Alert v-if="hasLimitedFields" variant="default" class="mb-6 border-error-600">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle>{{ t('views.new-desktop.step-2.hardware-limited.title') }}</AlertTitle>
        <AlertDescription>
          {{ t('views.new-desktop.step-2.hardware-limited.description') }}
          <ul v-if="restrictedFieldsDetails.length" class="mt-3 space-y-2">
            <li v-for="field in restrictedFieldsDetails" :key="field.name" class="text-sm">
              <span class="font-semibold text-error-600">{{ field.name }}: </span>
              <span class="text-error-600">{{ field.oldValue }} → {{ field.newValue }}</span>
            </li>
          </ul>
        </AlertDescription>
      </Alert>

      <DomainHardwareSummary
        :vcpu="templateData?.vcpu"
        :memory="templateData?.memory"
        :disk-bus="hardwareSummaryDiskBus"
        :videos="hardwareSummaryVideos"
        :interfaces="hardwareSummaryInterfaces"
        :boot-order="hardwareSummaryBootOrder"
        :isos="hardwareSummaryIsos"
        :floppies="hardwareSummaryFloppies"
        :loading="templateLoading"
        :vgpu="hardwareSummaryVgpus"
      />
    </div>
    <Separator orientation="horizontal" class="my-6">
      <template #default>
        <Button
          hierarchy="secondary-gray"
          size="sm"
          :icon="showHardwareCustomization ? 'chevron-up' : 'chevron-down'"
          @click="toggleHardwareCustomization"
        >
          {{
            t(
              `views.new-desktop.step-2.hardware-summary.${showHardwareCustomization ? 'hide' : 'show'}-hardware-customization`
            )
          }}
        </Button>
      </template>
    </Separator>
    <div v-show="showHardwareCustomization" class="my-8">
      <h3 class="text-lg font-semibold text-gray-warm-900">
        {{ t('views.new-desktop.step-2.all-hardware.title') }}
      </h3>
      <p class="text-sm font-regular mb-6">
        {{ t('views.new-desktop.step-2.all-hardware.description') }}
      </p>
      <DomainHardwareForm ref="hardwareFormRef" :template-id="selectedTemplate?.id" />
    </div>
  </div>
</template>
