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
import { MAX_VGPU_PROFILES, isVgpuSelectable } from '@/lib/vgpuSelection'

interface LimitedHardwareValue {
  old_value: unknown
  new_value: unknown
}

type LimitedHardware = Record<string, LimitedHardwareValue>

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
  enabled: computed(() => !!props.templateId)
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
const vcpus = computed(
  () => templateData.value?.hardware.vcpus || desktopData.value?.hardware.vcpus || props.vcpus
)
const memory = computed(
  () => templateData.value?.hardware.memory || desktopData.value?.hardware.memory || props.memory
)
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
  )
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

const formSchema = z.object({
  vcpus: z
    .number()
    .min(1)
    .refine(
      (val) => {
        const maxVcpus = userAllowedHardware.value?.quota?.vcpus ?? 128
        return val <= maxVcpus
      },
      { message: t('components.domain.hardware.limited.quota') }
    ),
  memory: z
    .number()
    .min(0.1)
    .refine(
      (val) => {
        const maxMemory = userAllowedHardware.value?.quota?.memory ?? 128
        return val <= maxMemory
      },
      { message: t('components.domain.hardware.limited.quota') }
    ),
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

// Fetch user allowed hardware options

const { isPending: userAllowedHardwareLoading, data: userAllowedHardware } = useQuery(
  getAllowedHardwareOptions()
)

const diskBusOptions = computed(() => userAllowedHardware.value?.disk_bus || [])
const videosOptions = computed(() => userAllowedHardware.value?.videos || [])
const bootsOptions = computed(() => userAllowedHardware.value?.boot_order || [])
const isosOptions = computed(() => userAllowedHardware.value?.isos || [])
const floppiesOptions = computed(() => userAllowedHardware.value?.floppies || [])
const vgpusOptions = computed(() => userAllowedHardware.value?.reservables.vgpus || [])

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
// Comma-separated names of the currently-selected vGPU profiles, for the trigger
// summary (reka-ui's SelectValue doesn't render a multiple selection).
const vgpuSummary = (ids: string[] | undefined): string => {
  const selected = ids ?? []
  return (vgpusOptions.value as VgpuOption[])
    .filter((o) => selected.includes(o.id))
    .map((o) => o.name)
    .join(', ')
}

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

const isLimited = (fieldName: string) => {
  return !!(computedLimitedHardware.value && computedLimitedHardware.value[fieldName])
}

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

const getLimitedMessage = (fieldName: string) => {
  const limited = computedLimitedHardware.value?.[fieldName]
  if (!limited) return ''

  return t('components.domain.hardware.limited.restricted', {
    old_value: formatValue(limited.old_value),
    new_value: formatValue(limited.new_value)
  })
}

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

const isFormValid = form.useStore((state) => state.isValid)

const interfacesStore = form.useStore((state) => state.values.interfaces)

function getInterfaces(): string[] {
  return (form.getFieldValue('interfaces') as string[] | undefined) ?? []
}

function addInterface(ifaceId: string) {
  const current = getInterfaces()
  if (current.includes(ifaceId)) return
  // Only add if the interface is available in the allowed-hardware catalog
  const available = networksOptions.value.some((iface) => iface.id === ifaceId)
  if (!available) return
  form.setFieldValue('interfaces', [...current, ifaceId])
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
      <section
        class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR] md:gap-0"
      >
        <div class="flex flex-row-reverse justify-end items-center gap-2.5">
          <h4 class="text-lg font-semibold text-gray-warm-900">
            {{ t('components.domain.hardware.hardwareGroups.system') }}
          </h4>
          <Icon name="hdd-02" />
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
              <InputField
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :destructive="isInvalid(field)"
                :placeholder="t('components.domain.hardware.vcpus.placeholder')"
                autocomplete="off"
                type="number"
                @blur="field.handleBlur"
                @input="field.handleChange(Number(($event.target as HTMLInputElement).value))"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              <FieldDescription
                v-if="isLimited('vcpus')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('vcpus') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="memory">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.memory.label') }}
              </FieldLabel>
              <InputField
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :destructive="isInvalid(field)"
                :placeholder="t('components.domain.hardware.memory.placeholder')"
                autocomplete="off"
                type="number"
                @blur="field.handleBlur"
                @input="field.handleChange(Number(($event.target as HTMLInputElement).value))"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              <FieldDescription
                v-if="isLimited('memory')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('memory') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
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
                <SelectTrigger
                  :aria-invalid="isInvalid(field) || isLimited('disk_bus')"
                  class="min-w-[120px]"
                >
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
              <FieldDescription v-if="isLimited('disk_bus')" class="text-destructive">
                {{ getLimitedMessage('disk_bus') }}
              </FieldDescription>
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
                <SelectTrigger
                  :aria-invalid="isInvalid(field) || isLimited('videos')"
                  class="min-w-[120px]"
                >
                  <SelectValue :placeholder="t('components.domain.hardware.videos.placeholder')" />
                </SelectTrigger>
                <SelectContent position="item-aligned">
                  <SelectItem v-for="video in videosOptions" :key="video.id" :value="video.id">
                    {{ video.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <FieldDescription
                v-if="isLimited('videos')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('videos') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
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
              <FieldDescription
                v-if="isLimited('boot_order')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('boot_order') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
            </Field>
          </form.Field>
        </div>
      </section>
      <section
        v-if="props.showPeripherals"
        class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR] md:gap-0"
      >
        <div class="flex flex-row-reverse justify-end items-center gap-2.5">
          <h4 class="text-lg font-semibold text-gray-warm-900">
            {{ t('components.domain.hardware.hardwareGroups.peripherals') }}
          </h4>
          <Icon name="hdd" />
        </div>
        <div class="grid grid-cols-1 gap-2.5 md:gap-5 md:grid-cols-2">
          <form.Field v-slot="{ field }" name="isos">
            <Field>
              <FieldLabel :for="field.name">
                {{ $t('components.domain.hardware.isos.label') }}
              </FieldLabel>
              <SearchableTags
                :tags="isosOptions.map((iso) => ({ label: iso.name, value: iso.id }))"
                :placeholder="t('components.domain.hardware.isos.placeholder')"
                :model-value="field.state.value"
                @update:model-value="field.handleChange($event)"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              <FieldDescription
                v-if="isLimited('isos')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('isos') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
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
              <FieldDescription
                v-if="isLimited('floppies')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon name="alert-circle" class="inline" size="sm" stroke-color="destructive" />
                        {{ getLimitedMessage('floppies') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
            </Field>
          </form.Field> -->
        </div>
      </section>
      <section
        class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR] md:gap-0"
      >
        <div class="flex flex-row-reverse justify-end items-center gap-2.5">
          <h4 class="text-lg font-semibold text-gray-warm-900">
            {{ t('components.domain.hardware.hardwareGroups.reservables') }}
          </h4>
          <Icon name="gpu" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2">
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
                  <span v-if="(field.state.value ?? []).length" class="truncate text-left">
                    {{ vgpuSummary(field.state.value) }}
                  </span>
                  <span v-else class="text-muted-foreground">
                    {{ t('components.domain.hardware.vgpus.placeholder') }}
                  </span>
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
              <FieldDescription
                v-if="isLimited('reservables.vgpus')"
                class="text-destructive flex items-center gap-1"
              >
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <div class="flex items-center gap-1">
                        <Icon
                          name="alert-circle"
                          class="inline"
                          size="sm"
                          stroke-color="destructive"
                        />
                        {{ getLimitedMessage('vgpus') }}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="$t('components.domain.hardware.limited.warning.title')"
                      :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                      side="top"
                    />
                  </Tooltip>
                </TooltipProvider>
              </FieldDescription>
            </Field>
          </form.Field>
        </div>
      </section>
      <form.Field v-slot="{ field }" name="interfaces">
        <Field>
          <FieldLabel :for="field.name">
            {{ $t('components.domain.hardware.networks.label') }}
          </FieldLabel>
          <FieldDescription
            v-if="isLimited('interfaces')"
            class="text-destructive flex items-center gap-1"
          >
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <div class="flex items-center gap-1">
                    <Icon name="alert-circle" class="inline" size="sm" stroke-color="destructive" />
                    {{ getLimitedMessage('interfaces') }}
                  </div>
                </TooltipTrigger>
                <TooltipContent
                  :title="$t('components.domain.hardware.limited.warning.title')"
                  :subtitle="$t('components.domain.hardware.limited.warning.subtitle')"
                  side="top"
                />
              </Tooltip>
            </TooltipProvider>
          </FieldDescription>
          <div class="flex flex-col gap-2">
            <!-- Add button to open modal -->
            <Button
              type="button"
              hierarchy="link-color"
              size="md"
              class="cursor-pointer"
              icon="edit-02"
              @click="showNetworksModal = true"
            >
              {{ t('components.domain.hardware.networks.label') }}
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
    </FieldGroup>
  </form>
</template>
