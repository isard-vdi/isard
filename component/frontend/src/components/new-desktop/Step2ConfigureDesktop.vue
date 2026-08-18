<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { useUserStore } from '@/stores/user'
import { getTemplateDetailsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const { t } = useI18n()
const userStore = useUserStore()

interface Template {
  id: string
  image?: DomainImageOutput
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
      image: DomainImageOutput | undefined
    }
  ]
}>()

// Sent explicitly, or the backend derives an unrelated stock card from the
// new desktop's id and the preview lies.
const selectedImage = ref<DomainImageOutput | undefined>(props.selectedTemplate?.image)
const showChangeImageModal = ref(false)

watch(
  () => props.selectedTemplate,
  (template) => {
    selectedImage.value = template?.image
  }
)

function handleImageSelected(image: DomainImageOutput) {
  selectedImage.value = image
}

// Fetch selected template info when selectedTemplate changes (feeds the summaries)
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

// The summary types its credentials as optional strings; the template response
// returns nullable ones.
const accessCredentials = computed(() => ({
  username: templateData.value?.credentials?.username ?? undefined,
  password: templateData.value?.credentials?.password ?? undefined
}))

const accessFormRef = ref<{ getFormData: () => Record<string, unknown>; isValid: boolean } | null>(
  null
)
const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  limitedFields: Record<string, unknown> | null
  getInterfaces: () => string[]
  addInterface: (ifaceId: string) => boolean | undefined
  removeInterface: (ifaceId: string) => void
  interfaces: string[]
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  return hardwareFormRef.value?.addInterface(ifaceId)
}
const hardwareFormIsValid = computed(() => {
  return hardwareFormRef.value?.isValid ?? true
})
const showConfiguration = ref(false)
const disclosureRef = ref<HTMLElement | null>(null)
const desktopKind = ref<'persistent' | 'nonpersistent'>('persistent')

// The configuration section headers take the accent of the selected kind, the
// same pairing the desktop cards and badges use elsewhere.
const kindAccent = computed(() =>
  desktopKind.value === 'persistent'
    ? { header: 'bg-secondary-3-300 text-secondary-3-600', icon: 'secondary-3-600' }
    : { header: 'bg-secondary-1-300 text-secondary-1-600', icon: 'secondary-1-600' }
)

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

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

/** Breathing room between the app header and whatever we scroll to. */
const SCROLL_GAP = 25

function stickyHeaderHeight(): number {
  const header = document.querySelector('main > header')
  if (!(header instanceof HTMLElement)) return 0
  return getComputedStyle(header).position === 'sticky' ? header.offsetHeight : 0
}

const openConfiguration = async () => {
  showConfiguration.value = true

  await nextTick()
  const target = disclosureRef.value
  if (!target) return
  const top =
    target.getBoundingClientRect().top + window.scrollY - stickyHeaderHeight() - SCROLL_GAP
  window.scrollTo({ top, behavior: scrollBehavior() })
}

const handleNotImplemented = () => alert('not implemented yet')

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
    hardwareSettings,
    image: selectedImage.value
  })
}

defineExpose({
  handleSubmit,
  areFormsValid
})
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :current-image="selectedImage"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <div class="flex flex-col gap-10">
    <div class="flex flex-col flex-col-reverse lg:flex-row justify-center gap-12">
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.new-desktop.step-2.preview.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.new-desktop.step-2.preview.description') }}
        </p>
        <div v-if="templateLoading" class="flex flex-col gap-2">
          <DesktopCardSkeleton class="w-[520px] h-[370px]" />
        </div>
        <template v-else>
          <DesktopCardBase :image-url="selectedImage?.url || ''" :desktop-kind="desktopKind">
            <template #header-actions>
              <Button
                icon="image-plus"
                hierarchy="secondary-gray"
                size="sm"
                :aria-label="t('components.change-image-modal.title')"
                @click="showChangeImageModal = true"
              />
            </template>
            <template #header>
              <DesktopCardHeader
                :name="infoFormValues.name"
                :description="infoFormValues.description"
              />
            </template>
            <template #footer>
              <Tooltip>
                <TooltipTrigger as-child>
                  <span
                    role="button"
                    aria-disabled="true"
                    tabindex="0"
                    :aria-label="t('components.desktops.desktop-card.status.stopped.action')"
                    class="inline-flex shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand"
                  >
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
                  </span>
                </TooltipTrigger>
                <TooltipContent
                  :title="t('views.new-desktop.step-2.preview.start-disabled')"
                  side="top"
                />
              </Tooltip>
            </template>
          </DesktopCardBase>
        </template>
      </div>
      <div class="flex-1">
        <div class="mb-6">
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
            direction="flex-row"
            :hide-description="true"
          />
        </div>
        <div>
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
                  :aria-label="t('components.domain.info.name.label')"
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
                class="bg-base-white resize-none h-25"
                :aria-label="t('components.domain.info.description.label')"
                :placeholder="t('components.domain.info.description.placeholder')"
                @update:model-value="(value) => field.handleChange(String(value))"
              />
            </desktopInfoForm.Field>
          </div>
        </div>
      </div>
    </div>
    <div>
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
      <div>
        <Separator class="my-12">
          <Button
            hierarchy="secondary-gray"
            size="sm"
            icon="edit-02"
            :aria-expanded="showConfiguration"
            aria-controls="desktop-configuration-panel"
            @click="openConfiguration"
          >
            {{ t('views.new-desktop.step-2.desktop-configuration.show') }}
          </Button>
        </Separator>
      </div>
      <Transition
        enter-active-class="transition-opacity duration-200 ease-out motion-reduce:transition-none"
        enter-from-class="opacity-0"
      >
        <div
          v-show="showConfiguration"
          id="desktop-configuration-panel"
          ref="disclosureRef"
          class="mb-10"
        >
          <!-- `items-end` keeps the action on the baseline of the two-line block. -->
          <div class="flex justify-between items-end gap-4 mb-5">
            <div>
              <h3 class="text-lg font-semibold text-gray-warm-900">
                {{ t('views.new-desktop.step-2.desktop-configuration.title') }}
              </h3>
              <p class="text-sm font-regular mt-1">
                {{ t('views.new-desktop.step-2.desktop-configuration.description') }}
              </p>
            </div>
            <Tooltip>
              <TooltipTrigger as-child>
                <span
                  role="button"
                  aria-disabled="true"
                  tabindex="0"
                  :aria-label="t('views.new-desktop.step-2.desktop-configuration.restore')"
                  class="inline-flex shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-error"
                >
                  <Button
                    hierarchy="link-destructive"
                    size="sm"
                    icon="refresh-ccw-01"
                    disabled
                    @click="handleNotImplemented"
                  >
                    {{ t('views.new-desktop.step-2.desktop-configuration.restore') }}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent
                :title="t('views.new-desktop.step-2.desktop-configuration.restore-disabled')"
                side="top"
              />
            </Tooltip>
          </div>
          <Skeleton v-if="templateLoading" class="h-48 w-full rounded-2xl" />
          <div
            v-else
            class="flex flex-col gap-4 bg-gray-warm-50 p-6 rounded-lg border border-gray-warm-200 shadow-xs"
          >
            <DomainAccessSummary
              class="border-0 bg-transparent rounded-none px-0 py-0"
              :credentials="accessCredentials"
              :viewers="templateData?.viewers"
              :fullscreen="templateData?.fullscreen"
            />
            <!-- No floppies: template details does not report them, unlike the
               desktop endpoint. -->
            <DomainHardwareSummary
              class="border-0 bg-transparent rounded-none px-0 py-0"
              :vcpu="templateData?.vcpu"
              :memory="templateData?.memory"
              :disk-bus="templateData?.disk_bus"
              :videos="templateData?.videos?.map((video) => video.name)"
              :interfaces="templateData?.interfaces?.map((iface) => iface.name)"
              :boot-order="templateData?.boot_order?.map((boot) => boot.name)"
              :isos="templateData?.isos?.map((iso) => iso.name)"
              :loading="templateLoading"
              :vgpus="templateData?.reservables?.vgpus"
            />
          </div>

          <div
            class="mt-6 flex flex-col gap-5 border border-gray-warm-200 rounded-lg overflow-hidden shadow-xs bg-gray-warm-50"
          >
            <div>
              <div :class="['flex gap-6 items-center px-4 py-3', kindAccent.header]">
                <div class="flex gap-3 items-center">
                  <Icon
                    name="lock-01"
                    size="lg"
                    :stroke-color="kindAccent.icon"
                    aria-hidden="true"
                  />
                  <h4 class="text-md font-semibold">
                    {{ t('views.new-desktop.step-2.all-access.title') }}
                  </h4>
                </div>
                <Icon
                  name="chevron-right"
                  size="xs"
                  :stroke-color="kindAccent.icon"
                  aria-hidden="true"
                />
                <p class="text-sm font-regular">
                  {{ t('views.new-desktop.step-2.all-access.description') }}
                </p>
              </div>
              <DomainAccessForm
                ref="accessFormRef"
                :template-id="selectedTemplate?.id"
                :show-bastion-config="false"
                :hardware-interfaces="hardwareInterfaces"
                :on-request-add-interface="handleAddInterfaceFromAccessForm"
                class="p-6"
              />
            </div>
            <div>
              <div :class="['flex gap-6 items-center px-4 py-3 rounded-t-lg', kindAccent.header]">
                <div class="flex gap-3 items-center">
                  <Icon name="cpu" size="lg" :stroke-color="kindAccent.icon" aria-hidden="true" />
                  <h4 class="text-lg font-semibold">
                    {{ t('views.new-desktop.step-2.all-hardware.title') }}
                  </h4>
                </div>
                <Icon
                  name="chevron-right"
                  size="xs"
                  :stroke-color="kindAccent.icon"
                  aria-hidden="true"
                />
                <p class="text-sm font-regular">
                  {{ t('views.new-desktop.step-2.all-hardware.description') }}
                </p>
              </div>
              <DomainHardwareForm
                ref="hardwareFormRef"
                :template-id="selectedTemplate?.id"
                class="p-6"
              />
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>
