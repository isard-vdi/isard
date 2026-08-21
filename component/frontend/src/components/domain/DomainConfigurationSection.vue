<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainSummary, { type DomainSummaryData } from '@/components/domain/DomainSummary.vue'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { AccessFormData, HardwareFormData } from '@/lib/domainPayload'
import type { DomainKind } from '@/components/domain/DomainInfoSection.vue'

export type DomainConfigurationContext =
  | 'new-desktop'
  | 'new-desktop-from-media'
  | 'edit-desktop'
  | 'edit-template'

/** Seeds for the sub-forms when there is no template or desktop to read from. */
export interface DomainConfigurationDefaults {
  access?: {
    credentials?: { username: string; password: string }
    fullscreen?: boolean
    viewers?: string[]
  }
  hardware?: {
    vcpus?: number
    memory?: number
    diskSize?: number
    diskBus?: string
    videos?: string
    bootOrder?: string
    isos?: string[]
    floppies?: string[]
    interfaces?: string[]
    reservables?: { vgpus?: string[] }
  }
}

const props = withDefaults(
  defineProps<{
    templateId?: string
    desktopId?: string
    loading?: boolean
    /** Edit views drop the disclosure and render the forms straight away. */
    alwaysOpen?: boolean
    showBastionConfig?: boolean
    showCustomDomains?: boolean
    showDiskSize?: boolean
    showPeripherals?: boolean
    summary?: DomainSummaryData
    defaults?: DomainConfigurationDefaults
    kind?: DomainKind
    entity?: 'desktops' | 'templates'
    /** Picks the blurb that explains where these values come from. */
    context?: DomainConfigurationContext
  }>(),
  {
    templateId: undefined,
    desktopId: undefined,
    loading: false,
    alwaysOpen: false,
    showBastionConfig: false,
    showCustomDomains: false,
    showDiskSize: false,
    showPeripherals: true,
    summary: undefined,
    defaults: undefined,
    kind: 'persistent',
    entity: 'desktops',
    context: 'new-desktop'
  }
)

const { t } = useI18n()

const accessFormRef = ref<InstanceType<typeof DomainAccessForm> | null>(null)
const hardwareFormRef = ref<InstanceType<typeof DomainHardwareForm> | null>(null)

const removedViewers = computed<string[]>(() => accessFormRef.value?.removedViewers ?? [])
const removedViewerLabels = computed<string[]>(() => accessFormRef.value?.removedViewerLabels ?? [])

// The summaries come from endpoints that don't apply the wireguard filter the
// access form does, so they would still offer viewers that won't be created.
const summaryViewers = computed(() =>
  (props.summary?.viewers ?? []).filter((viewer) => !removedViewers.value.includes(viewer))
)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  return hardwareFormRef.value?.addInterface(ifaceId)
}

const limitedFields = computed(() => hardwareFormRef.value?.limitedFields ?? null)

const hasLimitedFields = computed(() => {
  const fields = limitedFields.value
  return !!(fields && typeof fields === 'object' && Object.keys(fields).length > 0)
})

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

interface LimitedHardwareValue {
  old_value: unknown
  new_value: unknown
}

const restrictedFieldsDetails = computed(() => {
  const fields = limitedFields.value as Record<string, LimitedHardwareValue> | null
  if (!fields || typeof fields !== 'object') return []

  const fieldNameMap: Record<string, string> = {
    vcpus: t('components.domain.hardware.vcpus.label'),
    memory: t('components.domain.hardware.memory.label'),
    disk_bus: t('components.domain.hardware.disk-bus.label'),
    videos: t('components.domain.hardware.videos.label'),
    boot_order: t('components.domain.hardware.boot-order.label'),
    isos: t('components.domain.hardware.isos.label'),
    floppies: t('components.domain.hardware.floppies.label'),
    vgpus: t('components.domain.hardware.vgpus.label'),
    interfaces: t('components.domain.hardware.networks.label')
  }

  return Object.entries(fields).map(([key, value]) => ({
    name: fieldNameMap[key] || key,
    oldValue: formatValue(value.old_value),
    newValue: formatValue(value.new_value)
  }))
})

// The section headers take the accent of the selected kind, the same pairing
// the desktop cards and badges use elsewhere.
const kindAccent = computed(() => {
  switch (props.kind) {
    case 'nonpersistent':
      return { header: 'bg-secondary-1-300 text-secondary-1-600', icon: 'secondary-1-600' }
    case 'deployment':
      return { header: 'bg-secondary-2-300 text-secondary-2-600', icon: 'secondary-2-600' }
    default:
      return { header: 'bg-secondary-3-300 text-secondary-3-600', icon: 'secondary-3-600' }
  }
})

const showConfiguration = ref(false)
const isOpen = computed(() => props.alwaysOpen || showConfiguration.value)
const disclosureRef = ref<HTMLElement | null>(null)

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

const open = async () => {
  showConfiguration.value = true

  await nextTick()
  const target = disclosureRef.value
  if (!target) return
  const top =
    target.getBoundingClientRect().top + window.scrollY - stickyHeaderHeight() - SCROLL_GAP
  window.scrollTo({ top, behavior: scrollBehavior() })
}

const isValid = computed(
  () => (hardwareFormRef.value?.isValid ?? true) && (accessFormRef.value?.isValid ?? true)
)

const isDirty = computed(() => !!accessFormRef.value?.isDirty || !!hardwareFormRef.value?.isDirty)

const reset = () => {
  accessFormRef.value?.reset()
  hardwareFormRef.value?.reset()
}

// A disabled button is not focusable, so the wrapper stands in as the trigger.
const restoreTriggerAttrs = computed<Record<string, unknown>>(() =>
  isDirty.value ? {} : { role: 'button', 'aria-disabled': 'true', tabindex: 0 }
)

const getFormData = () => ({
  access: accessFormRef.value?.getFormData() as AccessFormData | undefined,
  hardware: hardwareFormRef.value?.getFormData() as HardwareFormData | undefined
})

defineExpose({
  getFormData,
  isValid,
  isDirty,
  reset,
  open,
  removedViewerLabels,
  limitedFields
})
</script>

<template>
  <div>
    <Alert
      v-if="removedViewerLabels.length && !isOpen"
      variant="default"
      class="mb-6 border-error-600"
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
    <Alert v-if="hasLimitedFields" variant="default" class="mb-6 border-error-600">
      <FeaturedIconOutline kind="outline" color="error" />
      <AlertTitle>{{ t('components.domain.configuration.hardware-limited.title') }}</AlertTitle>
      <AlertDescription>
        {{ t('components.domain.configuration.hardware-limited.description') }}
        <ul v-if="restrictedFieldsDetails.length" class="mt-3 space-y-2">
          <li v-for="field in restrictedFieldsDetails" :key="field.name" class="text-sm">
            <span class="font-semibold text-error-600">{{ field.name }}: </span>
            <span class="text-error-600">{{ field.oldValue }} → {{ field.newValue }}</span>
          </li>
        </ul>
      </AlertDescription>
    </Alert>
    <div v-if="!alwaysOpen">
      <Separator class="my-12">
        <Button
          hierarchy="secondary-gray"
          size="sm"
          icon="edit-02"
          :aria-expanded="showConfiguration"
          aria-controls="domain-configuration-panel"
          @click="open"
        >
          {{ t('components.domain.configuration.section.show') }}
        </Button>
      </Separator>
    </div>
    <Transition
      enter-active-class="transition-opacity duration-200 ease-out motion-reduce:transition-none"
      enter-from-class="opacity-0"
    >
      <div v-show="isOpen" id="domain-configuration-panel" ref="disclosureRef" class="mb-10">
        <!-- `items-end` keeps the action on the baseline of the two-line block. -->
        <div class="flex justify-between items-end gap-4 mb-5">
          <div>
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t(`components.domain.configuration.section.title.${entity}`) }}
            </h3>
            <p class="text-sm font-regular mt-1">
              {{ t(`components.domain.configuration.section.description.${context}`) }}
            </p>
          </div>
          <Tooltip>
            <TooltipTrigger as-child>
              <span
                v-bind="restoreTriggerAttrs"
                class="inline-flex shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-error"
              >
                <Button
                  hierarchy="link-destructive"
                  size="sm"
                  icon="refresh-ccw-01"
                  :disabled="!isDirty"
                  @click="reset"
                >
                  {{ t('components.domain.configuration.section.restore') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent
              v-if="!isDirty"
              :title="t('components.domain.configuration.section.restore-disabled')"
              side="top"
            />
          </Tooltip>
        </div>
        <!-- `viewers` last: it overrides the ones the summary came with. -->
        <DomainSummary
          class="shadow-xs"
          :loading="loading"
          v-bind="summary"
          :viewers="summaryViewers"
        />

        <div
          class="mt-6 flex flex-col gap-5 border border-gray-warm-200 rounded-lg overflow-hidden shadow-xs bg-gray-warm-50"
        >
          <div>
            <div :class="['flex gap-6 items-center px-4 py-3', kindAccent.header]">
              <div class="flex gap-3 items-center">
                <Icon name="lock-01" size="lg" :stroke-color="kindAccent.icon" aria-hidden="true" />
                <h4 class="text-md font-semibold">
                  {{ t('components.domain.configuration.access.title') }}
                </h4>
              </div>
              <Icon
                name="chevron-right"
                size="xs"
                :stroke-color="kindAccent.icon"
                aria-hidden="true"
              />
              <p class="text-sm font-regular">
                {{ t('components.domain.configuration.access.description') }}
              </p>
            </div>
            <DomainAccessForm
              ref="accessFormRef"
              :template-id="templateId"
              :desktop-id="desktopId"
              :show-bastion-config="showBastionConfig"
              :show-custom-domains="showCustomDomains"
              :credentials="defaults?.access?.credentials"
              :fullscreen="defaults?.access?.fullscreen"
              :viewers="defaults?.access?.viewers"
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
                  {{ t('components.domain.configuration.hardware.title') }}
                </h4>
              </div>
              <Icon
                name="chevron-right"
                size="xs"
                :stroke-color="kindAccent.icon"
                aria-hidden="true"
              />
              <p class="text-sm font-regular">
                {{ t('components.domain.configuration.hardware.description') }}
              </p>
            </div>
            <DomainHardwareForm
              ref="hardwareFormRef"
              :template-id="templateId"
              :desktop-id="desktopId"
              :show-disk-size="showDiskSize"
              :show-peripherals="showPeripherals"
              :vcpus="defaults?.hardware?.vcpus"
              :memory="defaults?.hardware?.memory"
              :disk-bus="defaults?.hardware?.diskBus"
              :disk-size="defaults?.hardware?.diskSize"
              :videos="defaults?.hardware?.videos"
              :boot-order="defaults?.hardware?.bootOrder"
              :isos="defaults?.hardware?.isos"
              :floppies="defaults?.hardware?.floppies"
              :interfaces="defaults?.hardware?.interfaces"
              :reservables="defaults?.hardware?.reservables"
              class="p-6"
            />
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
