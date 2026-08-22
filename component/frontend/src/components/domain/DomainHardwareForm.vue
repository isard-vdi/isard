<script setup lang="ts">
import { revalidateLogic, useForm } from '@tanstack/vue-form'
import { useI18n } from 'vue-i18n'
import { InputField } from '@/components/input-field'
import { reactive, computed, ref, watch } from 'vue'
import { z } from 'zod'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel
} from '@/components/ui/field'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { useQuery } from '@tanstack/vue-query'
import {
  getAllowedHardwareOptions,
  getTemplateInfoOptions,
  getDesktopInfoOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { SearchableTags } from '@/components/searchable-tags'
import SelectNetworksModal from '@/components/modal/SelectNetworksModal.vue'
import { Button } from '@/components/ui/button'
import { MAX_VGPU_PROFILES, NO_VGPU_ID, isVgpuSelectable } from '@/lib/vgpuSelection'
import HardwareLimitChip from '@/components/domain/HardwareLimitChip.vue'
import type { LimitedHardware, LimitedHardwareValue } from '@/lib/hardwareLimits'
import {
  VCPU_TIERS,
  MEMORY_TIERS,
  buildTieredOptions,
  roundToNearestTier
} from '@/lib/hardwareTiers'

const emit = defineEmits<{
  'update:interfaces': [interfaces: string[]]
}>()

interface Props {
  loading?: boolean
  templateId?: string // Optional template ID to load hardware from
  desktopId?: string // Optional desktop ID to load hardware from
  showDiskSize?: boolean // Show disk size field (e.g. when creating from media)
  showPeripherals?: boolean // Show peripherals section (ISOs/floppies). Set to false when creating from media.
  // Also allow sending the default hardware values directly though props
  vcpus?: number
  memory?: number
  diskBus?: string
  diskSize?: number
  videos?: string // Currently a single value, but could be extended to multiple in the future (hence de plural name)
  bootOrder?: string // Currently a single value, but could be extended to multiple in the future (hence de plural name)
  isos?: string[]
  floppies?: string[]
  reservables?: {
    vgpus?: string[]
  }
  interfaces?: string[]
  limitedHardware?: LimitedHardware | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  templateId: undefined,
  desktopId: undefined,
  showDiskSize: false,
  showPeripherals: true,
  diskSize: 1,
  vcpus: 2,
  memory: 4,
  diskBus: 'default',
  videos: 'default',
  bootOrder: 'disk',
  isos: () => [],
  floppies: () => [],
  reservables: () => ({ vgpus: undefined }),
  interfaces: () => [],
  limitedHardware: null
})

// Fetch template info when templateId is provided
const {
  isPending: templateLoading,
  error: templateError,
  data: templateData
} = useQuery({
  ...getTemplateInfoOptions({
    path: {
      template_id: props.templateId!
    }
  }),
  enabled: computed(() => !!props.templateId),
  gcTime: 0
})

// Fetch desktop info when desktopId is provided
const {
  isPending: desktopLoading,
  error: desktopError,
  data: desktopData
} = useQuery({
  ...getDesktopInfoOptions({
    path: {
      desktop_id: props.desktopId!
    }
  }),
  enabled: computed(() => !!props.desktopId)
})

// Computed hardware values from template or desktop data or props
const vcpus = computed(() => {
  const raw = templateData.value?.hardware.vcpus || desktopData.value?.hardware.vcpus || props.vcpus
  return roundToNearestTier(raw, vcpuOptions.value)
})
const memory = computed(() => {
  const raw =
    templateData.value?.hardware.memory || desktopData.value?.hardware.memory || props.memory
  return roundToNearestTier(raw, memoryOptions.value)
})
const diskBus = computed(
  () =>
    templateData.value?.hardware.disk_bus || desktopData.value?.hardware.disk_bus || props.diskBus
)
const diskSize = computed(() => props.diskSize)
const videos = computed(() => {
  return (
    (templateData.value?.hardware.videos && templateData.value.hardware.videos[0]) ||
    (desktopData.value?.hardware.videos && desktopData.value.hardware.videos[0]) ||
    props.videos
  )
})
const bootOrder = computed(() => {
  return (
    (templateData.value?.hardware.boot_order && templateData.value.hardware.boot_order[0]) ||
    (desktopData.value?.hardware.boot_order && desktopData.value.hardware.boot_order[0]) ||
    props.bootOrder
  )
})
const isos = computed(() => {
  return (
    templateData.value?.hardware.isos?.map((iso) => iso.id) ||
    desktopData.value?.hardware.isos?.map((iso) => iso.id) ||
    props.isos
  )
})
const floppies = computed(() => {
  return (
    templateData.value?.hardware.floppies?.map((floppy) => floppy.id) ||
    desktopData.value?.hardware.floppies?.map((floppy) => floppy.id) ||
    props.floppies
  )
})
// A desktop may reserve several co-locatable vGPU profiles, so this is the full
// array (was `[0]` — single profile only). Empty array = no GPU.
const vgpus = computed<string[]>(() => {
  return (
    templateData.value?.reservables?.vgpus ||
    desktopData.value?.reservables?.vgpus ||
    props.reservables?.vgpus ||
    []
  ).filter((id) => id !== NO_VGPU_ID)
})
const interfaces = computed(() => {
  return (
    templateData.value?.hardware.interfaces?.map((i) => i.id) ||
    desktopData.value?.hardware.interfaces?.map((i) => i.id) ||
    props.interfaces
  )
})

const { t } = useI18n()

const maxDiskSize = computed(() => {
  const quota = userAllowedHardware.value?.quota
  if (!quota || typeof quota === 'boolean') return 500
  return (quota as Record<string, number>).desktops_disk_size ?? 500
})

const maxVcpus = computed(() => {
  const quota = userAllowedHardware.value?.quota
  if (!quota || typeof quota === 'boolean') return 128
  return (quota as Record<string, number>).vcpus ?? 128
})
const maxMemory = computed(() => {
  const quota = userAllowedHardware.value?.quota
  if (!quota || typeof quota === 'boolean') return 1024
  return (quota as Record<string, number>).memory ?? 1024
})
const vcpuOptions = computed(() => buildTieredOptions(maxVcpus.value, VCPU_TIERS))
const memoryOptions = computed(() => buildTieredOptions(maxMemory.value, MEMORY_TIERS))

const formSchema = z.object({
  vcpus: z
    .number()
    .min(1)
    .refine((val) => val <= maxVcpus.value, {
      message: t('components.domain.hardware.limited.quota')
    }),
  memory: z
    .number()
    .min(0.1)
    .refine((val) => val <= maxMemory.value, {
      message: t('components.domain.hardware.limited.quota')
    }),
  diskBus: z.string(),
  diskSize: props.showDiskSize
    ? z
        .number()
        .min(1)
        .refine((val) => val <= maxDiskSize.value, {
          message: t('components.domain.hardware.limited.quota')
        })
    : z.number().optional(),
  videos: z.string(),
  bootOrder: z.string(),
  isos: z.array(z.string()).optional(),
  floppies: z.array(z.string()),
  reservables: z.object({
    vgpus: z.array(z.string()).max(MAX_VGPU_PROFILES).optional()
  }),
  interfaces: z.array(z.string())
})

const defaultValues = reactive({
  vcpus,
  memory,
  diskBus,
  diskSize,
  videos,
  bootOrder,
  isos,
  floppies,
  reservables: {
    vgpus
  },
  interfaces
})

const form = useForm({
  defaultValues,
  validators: {
    onChange: formSchema
  }
})

// Re-seed when source data changes (e.g. stale cache replaced by fresh fetch),
// but never over edits in progress: the edit views refetch on focus.
watch([templateData, desktopData], () => {
  if (form.state.isPristine) form.reset()
})

const isDirty = form.useStore((state) => !state.isDefaultValue)

// Fetch user allowed hardware options

const { isPending: userAllowedHardwareLoading, data: userAllowedHardware } = useQuery(
  getAllowedHardwareOptions()
)

const diskBusOptions = computed(() => userAllowedHardware.value?.disk_bus || [])
const videosOptions = computed(() => userAllowedHardware.value?.videos || [])
const bootsOptions = computed(() => userAllowedHardware.value?.boot_order || [])
const isosOptions = computed(() => userAllowedHardware.value?.isos || [])
const floppiesOptions = computed(() => userAllowedHardware.value?.floppies || [])
const vgpusOptions = computed(
  () => userAllowedHardware.value?.reservables.vgpus.filter((v) => v.id !== NO_VGPU_ID) || []
)

// A vGPU (esp. passthrough) can be hosted on several hypervisors / NUMA sockets.
// The backend tags each option with its hypervisor groups + NUMA placement so
// the selector can group otherwise-identical cards by socket/host (matching the
// webapp / old-frontend). Admins/managers get real hypervisor names; other roles
// get anonymized group indices.
interface VgpuOption {
  id: string
  name: string
  hypervisor_groups?: number[]
  numa_by_group?: Record<string, number[]>
  hypervisors?: string[]
  numa_by_hypervisor?: Record<string, number[]>
}

// Label a card by its primary placement (lowest group/host, then lowest NUMA
// node) so it appears once, like the webapp's "listed under its lowest socket".
const vgpuGroupLabel = (v: VgpuOption): string | null => {
  const byHyp = v.numa_by_hypervisor || {}
  const byGroup = v.numa_by_group || {}
  const useNames = Object.keys(byHyp).length > 0
  const map: Record<string, number[]> = useNames ? byHyp : byGroup
  const keys = Object.keys(map)
  if (keys.length === 0) return null
  const primaryKey = useNames
    ? [...keys].sort()[0]
    : String([...keys].map(Number).sort((a, b) => a - b)[0])
  const host = useNames ? primaryKey : `#${primaryKey}`
  const nodes = [...(map[primaryKey] || [])].sort((a, b) => a - b)
  return nodes.length ? `${host} (NUMA ${nodes[0]})` : host
}

// Group the options only when there is more than one distinct placement
// (multi-socket / multi-hypervisor); otherwise present a single flat list.
const groupedVgpus = computed<{ label: string | null; items: VgpuOption[] }[]>(() => {
  const opts = vgpusOptions.value as VgpuOption[]
  const groups = new Map<string, VgpuOption[]>()
  for (const v of opts) {
    const key = vgpuGroupLabel(v) ?? ''
    const bucket = groups.get(key) ?? []
    bucket.push(v)
    groups.set(key, bucket)
  }
  const labelled = [...groups.keys()].filter((k) => k !== '')
  if (labelled.length <= 1) {
    return [{ label: null, items: opts }]
  }
  return [...groups.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, items]) => ({ label: label || null, items }))
})
// Grey out a profile that can't be added to the current selection (count limit
// reached or not co-locatable on a single hypervisor). The backend enforces the
// same rules; this just prevents obviously-invalid picks.
const vgpuDisabled = (option: VgpuOption, ids: string[] | undefined): boolean => {
  return !isVgpuSelectable(option, ids ?? [], vgpusOptions.value as VgpuOption[])
}

const networksOptions = computed(() => userAllowedHardware.value?.interfaces || [])

// Computed limited hardware from template or desktop data
const computedLimitedHardware = computed(() => {
  if (props.templateId && templateData.value) {
    return templateData.value.limited_hardware
  }
  if (props.desktopId && desktopData.value) {
    return desktopData.value.limited_hardware
  }
  return props.limitedHardware
})

const isInvalid = (field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) => {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

const limitedField = (fieldName: string): LimitedHardwareValue | null =>
  (computedLimitedHardware.value as LimitedHardware | null)?.[fieldName] ?? null

function getNamedResources(ids: string[] | undefined, options: { id: string; name: string }[]) {
  if (!ids) return undefined
  return ids.map((id) => {
    const item = options.find((option) => option.id === id)
    return {
      id,
      name: item?.name ?? id
    }
  })
}

// Add state for modal
const showNetworksModal = ref(false)

// Handler for saving networks
const handleSaveNetworks = (interfaces: string[]) => {
  form.setFieldValue('interfaces', interfaces)
}

// Expose method to get form data to parent components
const getFormData = () => ({
  vcpus: form.getFieldValue('vcpus'),
  memory: form.getFieldValue('memory'),
  diskBus: form.getFieldValue('diskBus'),
  ...(props.showDiskSize ? { diskSize: form.getFieldValue('diskSize') } : {}),
  videos: form.getFieldValue('videos'),
  bootOrder: form.getFieldValue('bootOrder'),
  isos: getNamedResources(form.getFieldValue('isos'), isosOptions.value),
  floppies: getNamedResources(form.getFieldValue('floppies'), floppiesOptions.value),
  interfaces: form.getFieldValue('interfaces'),
  reservables: {
    vgpus: (form.getFieldValue('reservables.vgpus') as string[] | undefined)?.length
      ? form.getFieldValue('reservables.vgpus')
      : null
  }
})

const formValues = form.useStore((state) => state.values)

const optionName = (id: string | undefined, options: { id: string; name: string }[]) =>
  id === undefined ? undefined : (options.find((option) => option.id === id)?.name ?? id)

const optionNames = (ids: string[] | undefined, options: { id: string; name: string }[]) =>
  ids?.map((id) => optionName(id, options) as string)

interface HardwareValues {
  vcpus?: number
  memory?: number
  diskBus?: string
  diskSize?: number
  videos?: string
  bootOrder?: string
  isos?: string[]
  floppies?: string[]
  interfaces?: string[]
  reservables?: { vgpus?: string[] }
}

/** What the summary card shows for this form, with ids resolved. */
const buildSummary = (values: HardwareValues) => ({
  vcpu: values.vcpus,
  memory: values.memory,
  diskBus: optionName(values.diskBus, diskBusOptions.value),
  diskSize: props.showDiskSize ? values.diskSize : undefined,
  videos: values.videos ? [optionName(values.videos, videosOptions.value) as string] : undefined,
  bootOrder: values.bootOrder
    ? [optionName(values.bootOrder, bootsOptions.value) as string]
    : undefined,
  isos: optionNames(values.isos, isosOptions.value),
  floppies: optionNames(values.floppies, floppiesOptions.value),
  interfaces: optionNames(values.interfaces, networksOptions.value),
  vgpus: optionNames(values.reservables?.vgpus, vgpusOptions.value) ?? null
})

const summary = computed(() => buildSummary(formValues.value))

/** The same, as the form was seeded: what the card compares the edits against. */
const baseSummary = computed(() => buildSummary(defaultValues))

const isFormValid = form.useStore((state) => state.isValid)

const interfacesStore = form.useStore((state) => state.values.interfaces)

function getInterfaces(): string[] {
  return (form.getFieldValue('interfaces') as string[] | undefined) ?? []
}

function addInterface(ifaceId: string): boolean | undefined {
  if (!userAllowedHardware.value) return undefined
  const current = getInterfaces()
  if (current.includes(ifaceId)) return true
  // Only add if the interface is available in the allowed-hardware catalog
  const available = networksOptions.value.some((iface) => iface.id === ifaceId)
  if (!available) return false
  form.setFieldValue('interfaces', [...current, ifaceId])
  return true
}

function removeInterface(ifaceId: string) {
  const current = getInterfaces()
  if (!current.includes(ifaceId)) return
  form.setFieldValue(
    'interfaces',
    current.filter((id) => id !== ifaceId)
  )
}

const wireguardAvailable = computed(() =>
  networksOptions.value.some((iface) => iface.id === 'wireguard')
)

watch(interfacesStore, (newInterfaces) => {
  emit('update:interfaces', [...(newInterfaces as string[])])
})

defineExpose({
  getFormData,
  isValid: isFormValid,
  isDirty,
  summary,
  baseSummary,
  reset: () => form.reset(),
  limitedFields: computedLimitedHardware,
  getInterfaces,
  addInterface,
  removeInterface,
  interfaces: interfacesStore,
  wireguardAvailable
})
</script>
<template>
  <template
    v-if="
      (props.templateId && templateLoading) ||
      (props.desktopId && desktopLoading) ||
      props.loading ||
      userAllowedHardwareLoading
    "
  >
    <div class="flex flex-col gap-2">
      <Skeleton class="h-10 w-32" />
      <Skeleton class="h-10 w-32" />
    </div>
  </template>
  <form v-else>
    <FieldGroup>
      <section class="group/hw-section grid gap-4 items-start">
        <div class="flex items-center gap-2">
          <Icon
            name="hdd-02"
            size="sm"
            stroke-color=""
            aria-hidden="true"
            class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
          />
          <h4
            class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
          >
            {{ t('components.domain.hardware.hardwareGroups.system') }}
          </h4>
          <Separator class="flex-1" />
        </div>
        <div
          :class="[
            'grid gap-2.5 md:gap-5 grid-cols-1 sm:grid-cols-2',
            props.showDiskSize ? 'lg:grid-cols-3' : 'lg:grid-cols-5'
          ]"
        >
          <form.Field v-slot="{ field }" name="vcpus">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.vcpus.label') }}
              </FieldLabel>
              <Select
                name="vcpus"
                :model-value="field.state.value"
                @update:model-value="field.handleChange"
              >
                <SelectTrigger
                  :id="field.name"
                  :aria-invalid="isInvalid(field)"
                  class="min-w-[120px]"
                >
                  <SelectValue :placeholder="t('components.domain.hardware.vcpus.placeholder')" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="option in vcpuOptions" :key="option" :value="option">
                    {{ option }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              <HardwareLimitChip :limited="limitedField('vcpus')" />
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="memory">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.memory.label') }}
              </FieldLabel>
              <Select
                name="memory"
                :model-value="field.state.value"
                @update:model-value="field.handleChange"
              >
                <SelectTrigger
                  :id="field.name"
                  :aria-invalid="isInvalid(field)"
                  class="min-w-[120px]"
                >
                  <SelectValue :placeholder="t('components.domain.hardware.memory.placeholder')" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="option in memoryOptions" :key="option" :value="option">
                    {{ option }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              <HardwareLimitChip :limited="limitedField('memory')" />
            </Field>
          </form.Field>
          <form.Field v-if="props.showDiskSize" v-slot="{ field }" name="diskSize">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.disk-size.label') }}
              </FieldLabel>
              <InputField
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :destructive="isInvalid(field)"
                :placeholder="t('components.domain.hardware.disk-size.placeholder')"
                autocomplete="off"
                type="number"
                @blur="field.handleBlur"
                @input="field.handleChange(Number(($event.target as HTMLInputElement).value))"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="diskBus">
            <Field>
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.disk-bus.label') }}
              </FieldLabel>
              <Select
                name="diskBus"
                :model-value="field.state.value"
                @update:model-value="field.handleChange"
              >
                <SelectTrigger :aria-invalid="isInvalid(field)" class="min-w-[120px]">
                  <SelectValue
                    :placeholder="t('components.domain.hardware.disk-bus.placeholder')"
                  />
                </SelectTrigger>
                <SelectContent position="item-aligned">
                  <SelectItem v-for="bus in diskBusOptions" :key="bus.id" :value="bus.id">
                    {{ bus.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <HardwareLimitChip :limited="limitedField('disk_bus')" />
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="videos">
            <Field>
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.videos.label') }}
              </FieldLabel>
              <Select
                name="videos"
                :model-value="field.state.value"
                @update:model-value="field.handleChange"
              >
                <SelectTrigger :aria-invalid="isInvalid(field)" class="min-w-[120px]">
                  <SelectValue :placeholder="t('components.domain.hardware.videos.placeholder')" />
                </SelectTrigger>
                <SelectContent position="item-aligned">
                  <SelectItem v-for="video in videosOptions" :key="video.id" :value="video.id">
                    {{ video.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <HardwareLimitChip :limited="limitedField('videos')" />
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="bootOrder">
            <Field>
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.boot-order.label') }}
              </FieldLabel>
              <Select
                name="bootOrder"
                :model-value="field.state.value"
                @update:model-value="field.handleChange"
              >
                <SelectTrigger :aria-invalid="isInvalid(field)" class="min-w-[120px]">
                  <SelectValue
                    :placeholder="t('components.domain.hardware.boot-order.placeholder')"
                  />
                </SelectTrigger>
                <SelectContent position="item-aligned">
                  <SelectItem v-for="boot in bootsOptions" :key="boot.id" :value="boot.id">
                    {{ boot.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <HardwareLimitChip :limited="limitedField('boot_order')" />
            </Field>
          </form.Field>
        </div>
      </section>
      <section class="grid grid-cols-1 gap-y-7 md:grid-cols-2 md:gap-x-10 items-start">
        <div v-if="props.showPeripherals" class="group/hw-section grid gap-4 items-start">
          <div class="flex items-center gap-2">
            <Icon
              name="hdd"
              size="sm"
              stroke-color=""
              aria-hidden="true"
              class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
            />
            <h4
              class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
            >
              {{ t('components.domain.hardware.hardwareGroups.peripherals') }}
            </h4>
            <Separator class="flex-1" />
          </div>
          <div class="grid grid-cols-1 gap-2.5 md:gap-5">
            <form.Field v-slot="{ field }" name="isos">
              <Field>
                <FieldLabel :for="field.name">
                  {{ $t('components.domain.hardware.isos.label') }}
                </FieldLabel>
                <SearchableTags
                  :tags="isosOptions.map((iso) => ({ label: iso.name, value: iso.id }))"
                  :placeholder="t('components.domain.hardware.isos.placeholder')"
                  :model-value="field.state.value"
                  tagsDisplay="wrap"
                  :invalid="isInvalid(field)"
                  @update:model-value="field.handleChange($event)"
                />
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
                <HardwareLimitChip :limited="limitedField('isos')" />
              </Field>
            </form.Field>
            <!-- TODO: Test how to add floppies to the system -->
            <!-- <form.Field name="floppies" #default="{ field }">
              <Field>
                <FieldLabel :for="field.name">
                  {{ $t('components.domain.hardware.floppies.label') }}
                </FieldLabel>
                <SearchableTags
                  :selected="field.state.value"
                  :tags="floppiesOptions.map((floppy) => ({ label: floppy.name, value: floppy.id }))"
                  :placeholder="t('components.domain.hardware.floppies.placeholder')"
                  @update:modelValue="field.handleChange"
                />
                <HardwareLimitChip :limited="limitedField('floppies')" />
              </Field>
            </form.Field> -->
          </div>
        </div>
        <div class="group/hw-section grid gap-4 items-start">
          <div class="flex items-center gap-2">
            <Icon
              name="gpu"
              size="sm"
              stroke-color=""
              aria-hidden="true"
              class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
            />
            <h4
              class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
            >
              {{ t('components.domain.hardware.hardwareGroups.reservables') }}
            </h4>
            <Separator class="flex-1" />
          </div>
          <div class="grid grid-cols-1">
            <form.Field v-slot="{ field }" name="reservables.vgpus">
              <Field>
                <FieldLabel :for="field.name">
                  {{ $t('components.domain.hardware.vgpus.label') }}
                </FieldLabel>
                <Select
                  name="reservables.vgpus"
                  multiple
                  :model-value="field.state.value ?? []"
                  @update:model-value="field.handleChange"
                >
                  <SelectTrigger :aria-invalid="isInvalid(field)" class="min-w-[120px]">
                    <SelectValue :placeholder="t('components.domain.hardware.vgpus.placeholder')" />
                  </SelectTrigger>
                  <SelectContent position="item-aligned">
                    <SelectGroup v-for="(grp, gi) in groupedVgpus" :key="gi">
                      <SelectLabel v-if="grp.label">{{ grp.label }}</SelectLabel>
                      <SelectItem
                        v-for="vgpu in grp.items"
                        :key="vgpu.id"
                        :value="vgpu.id"
                        :disabled="vgpuDisabled(vgpu, field.state.value)"
                      >
                        {{ vgpu.name }}
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <HardwareLimitChip :limited="limitedField('vgpus')" />
              </Field>
            </form.Field>
          </div>
        </div>
      </section>
      <section class="group/hw-section grid gap-4 items-start">
        <div class="flex items-center gap-2">
          <Icon
            name="modem-02"
            size="sm"
            stroke-color=""
            aria-hidden="true"
            class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
          />
          <h4
            class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
          >
            {{ t('components.domain.hardware.networks.label') }}
          </h4>
          <Separator class="flex-1" />
        </div>
        <form.Field v-slot="{ field }" name="interfaces">
          <Field>
            <HardwareLimitChip :limited="limitedField('interfaces')" />
            <div class="flex flex-col gap-2 items-start">
              <!-- Add button to open modal -->
              <Button
                type="button"
                hierarchy="link-color"
                size="md"
                class="cursor-pointer"
                icon="edit-02"
                @click="showNetworksModal = true"
              >
                {{ t('components.domain.hardware.networks.modal.title') }}
              </Button>

              <!-- Add modal -->
              <SelectNetworksModal
                :open="showNetworksModal"
                :selected-networks="field.state.value as string[]"
                :available-networks="networksOptions"
                @close="showNetworksModal = false"
                @save="handleSaveNetworks"
              />
            </div>
          </Field>
        </form.Field>
      </section>
    </FieldGroup>
  </form>
</template>
