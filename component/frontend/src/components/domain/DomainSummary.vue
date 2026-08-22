<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import SummaryValue from '@/components/domain/SummaryValue.vue'
import { cn } from '@/lib/utils'
import { hasWireguardRequiringViewer } from '@/lib/viewers'

// Access + hardware summary of a domain (desktop or template) in a single card.

/** What the card reports; whoever renders it collects these from its own source. */
export interface DomainSummaryData {
  // Access
  // Nullable fields: that is what the generated domain/template responses carry.
  credentials?: {
    username?: string | null
    password?: string | null
  } | null
  viewers?: string[]
  fullscreen?: boolean
  // bastion?:
  // Hardware
  vcpu?: number
  memory?: number
  diskBus?: string
  diskSize?: number
  videos?: string[]
  bootOrder?: string[]
  isos?: string[]
  floppies?: string[]
  vgpus?: string[] | null
  interfaces?: string[]
}

interface Props extends DomainSummaryData {
  // Card
  title?: string
  loading?: boolean
  /** What the fields held before the edits, when the card tracks live forms. */
  previous?: DomainSummaryData
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  credentials: undefined,
  viewers: undefined,
  vcpu: undefined,
  memory: undefined,
  bootOrder: undefined,
  diskBus: undefined,
  diskSize: undefined,
  videos: undefined,
  isos: undefined,
  floppies: undefined,
  vgpus: undefined,
  interfaces: undefined,
  title: undefined,
  previous: undefined,
  class: undefined
})

const { t } = useI18n()

const sameValue = (a: unknown, b: unknown) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** Renders a value against what its field held before the edits. */
function field<K extends keyof DomainSummaryData>(
  key: K,
  format: (value: DomainSummaryData[K]) => string
) {
  const before = props.previous?.[key]
  // A baseline that has not seeded itself is missing, not empty.
  const changed = before !== undefined && !sameValue(props[key], before)
  return { value: format(props[key]), changed, previous: changed ? format(before) : null }
}

function credential(name: 'username' | 'password') {
  const current = props.credentials?.[name] ?? ''
  const before = props.previous?.credentials?.[name]
  const changed = before !== undefined && before !== current
  return { value: current, changed, previous: changed ? before : null }
}

type ListKey = 'interfaces' | 'isos' | 'floppies'

const listItem = (key: ListKey, item: string) => {
  const before = props.previous?.[key]
  return { value: item, changed: before !== undefined && !before.includes(item) }
}

const removedItems = (key: ListKey) =>
  (props.previous?.[key] ?? []).filter((item) => !(props[key] ?? []).includes(item))

const list = (values?: string[] | null) => values?.join(', ') ?? ''
const text = (value?: string) => value ?? ''
const viewerLabels = (viewers?: string[]) =>
  (viewers ?? []).map((viewer) => t(`viewers.${viewer.toLowerCase().replace('_', '-')}`)).join(', ')
const fullscreenLabel = (enabled?: boolean) =>
  t(
    enabled
      ? 'components.domain-info-modal.fields.viewers.fullscreen-enabled'
      : 'components.domain-info-modal.fields.viewers.fullscreen-disabled'
  )
const vcpuLabel = (vcpu?: number) => `${vcpu} ${t('components.domain.hardware.vcpus.label')}`
const memoryLabel = (memory?: number) =>
  `${memory?.toFixed(2)} ${t('components.domain.hardware.memory.label')}`
const diskSizeLabel = (size?: number) =>
  `${size} ${t('components.domain.hardware.disk-size.label')}`

// Credentials only make sense for the viewers that go through Wireguard; the
// rest never surface them, so showing them there would be misleading.
const showCredentials = computed(
  () =>
    hasWireguardRequiringViewer(props.viewers ?? []) &&
    !!(props.credentials?.username || props.credentials?.password)
)

const hasViewers = computed(() => Boolean(props.viewers && props.viewers.length > 0))

const hasAccessInfo = computed(() => showCredentials.value || hasViewers.value)

const hasSystemInfo = computed(() => {
  return (
    props.vcpu || props.memory || props.diskSize || props.bootOrder || props.diskBus || props.videos
  )
})

const hasNetworks = computed(
  () => Boolean(props.interfaces?.length) || removedItems('interfaces').length > 0
)

const hasPeripherals = computed(
  () =>
    Boolean(props.isos?.length || props.floppies?.length) ||
    removedItems('isos').length > 0 ||
    removedItems('floppies').length > 0
)

const hasReservables = computed(() => Boolean(props.vgpus && props.vgpus.length > 0))

const hasHardwareInfo = computed(() => {
  return hasSystemInfo.value || hasNetworks.value || hasPeripherals.value || hasReservables.value
})
</script>

<template>
  <div
    :class="
      cn(
        'flex flex-col gap-6 bg-gray-warm-50 p-4 rounded-md border border-gray-warm-200',
        props.class
      )
    "
  >
    <h2 v-if="props.title" class="text-lg font-bold text-gray-warm-700">{{ props.title }}</h2>

    <!-- Loading skeleton -->
    <template v-if="props.loading">
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-6">
        <div class="flex flex-col gap-4">
          <div class="flex items-center gap-2.5">
            <Skeleton class="h-4 w-20" />
            <Skeleton class="flex-1 h-px" />
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-3">
            <Skeleton class="h-5 w-20" />
            <Skeleton class="h-5 w-16" />
          </div>
        </div>
        <div class="flex flex-col sm:col-span-3 gap-4">
          <div class="flex items-center gap-2.5">
            <Skeleton class="h-4 w-16" />
            <Skeleton class="flex-1 h-px" />
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-3">
            <Skeleton class="h-5 w-24" />
            <Skeleton class="h-5 w-32" />
          </div>
        </div>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <div class="flex flex-col sm:col-span-2 gap-4">
          <div class="flex items-center gap-2.5">
            <Skeleton class="h-4 w-16" />
            <Skeleton class="flex-1 h-px" />
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-3">
            <Skeleton class="h-5 w-20" />
            <Skeleton class="h-5 w-24" />
            <Skeleton class="h-5 w-16" />
          </div>
        </div>
        <div class="flex flex-col gap-4">
          <div class="flex items-center gap-2.5">
            <Skeleton class="h-4 w-16" />
            <Skeleton class="flex-1 h-px" />
          </div>
          <Skeleton class="h-5 w-28" />
        </div>
      </div>
    </template>

    <!-- Content -->
    <template v-else>
      <!-- Access -->
      <div v-if="hasAccessInfo" class="grid grid-cols-1 sm:grid-cols-4 gap-6">
        <!-- Credentials -->
        <div
          v-if="showCredentials"
          class="flex flex-col gap-4"
          :class="hasViewers ? '' : 'sm:col-span-4'"
        >
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-access-summary.credentials.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div class="flex flex-wrap items-center gap-x-8 gap-y-3">
            <div v-if="props.credentials?.username" class="flex items-center gap-2">
              <Icon name="user-03" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="credential('username')" />
            </div>
            <div v-if="props.credentials?.password" class="flex items-center gap-2">
              <Icon name="passcode-lock" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="credential('password')" />
            </div>
          </div>
        </div>

        <!-- Viewers -->
        <div
          v-if="hasViewers"
          class="flex flex-col gap-4"
          :class="showCredentials ? 'sm:col-span-3' : 'sm:col-span-4'"
        >
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-access-summary.viewers.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div class="flex items-center gap-2">
              <Icon name="expand-06" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('fullscreen', fullscreenLabel)" />
            </div>
            <div class="flex items-center gap-2">
              <Icon name="monitor" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('viewers', viewerLabels)" />
            </div>
          </div>
        </div>
      </div>

      <!-- Hardware -->
      <div v-if="hasHardwareInfo" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <!-- System -->
        <div v-if="hasSystemInfo" class="flex flex-col sm:col-span-2 gap-4">
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-hardware-summary.system.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div v-if="props.vcpu" class="flex items-center gap-2">
              <Icon name="cpu" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('vcpu', vcpuLabel)" />
            </div>
            <div v-if="props.memory" class="flex items-center gap-2">
              <Icon name="memory" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('memory', memoryLabel)" />
            </div>
            <div v-if="props.diskSize" class="flex items-center gap-2">
              <Icon name="hdd" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('diskSize', diskSizeLabel)" />
            </div>
            <div v-if="props.bootOrder" class="flex items-center gap-2">
              <Icon name="hdd" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('bootOrder', list)" />
            </div>
            <div v-if="props.diskBus" class="flex items-center gap-2">
              <Icon name="hdd-02" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('diskBus', text)" />
            </div>
            <div v-if="props.videos" class="flex items-center gap-2">
              <Icon name="wires" size="md" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="field('videos', list)" />
            </div>
          </div>
        </div>

        <!-- Networks -->
        <div v-if="hasNetworks" class="flex flex-col gap-4">
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-hardware-summary.networks.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-3">
            <Icon name="modem-02" size="sm" stroke-color="gray-warm-700" />
            <div v-for="network in props.interfaces" :key="network" class="flex items-center gap-2">
              <SummaryValue v-bind="listItem('interfaces', network)" />
            </div>
            <div
              v-for="network in removedItems('interfaces')"
              :key="`removed-${network}`"
              class="flex items-center gap-2"
            >
              <SummaryValue :value="network" removed />
            </div>
          </div>
        </div>

        <!-- Peripherals/ISOs -->
        <div v-if="hasPeripherals" class="flex flex-col gap-4">
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-hardware-summary.peripherals.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-3">
            <div v-for="iso in props.isos" :key="iso" class="flex items-center gap-2">
              <Icon name="disc-02" size="sm" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="listItem('isos', iso)" />
            </div>
            <div
              v-for="iso in removedItems('isos')"
              :key="`removed-${iso}`"
              class="flex items-center gap-2"
            >
              <Icon name="disc-02" size="sm" stroke-color="gray-warm-400" />
              <SummaryValue :value="iso" removed />
            </div>
            <div v-for="floppy in props.floppies" :key="floppy" class="flex items-center gap-2">
              <Icon name="save-01" size="sm" stroke-color="gray-warm-700" />
              <SummaryValue v-bind="listItem('floppies', floppy)" />
            </div>
            <div
              v-for="floppy in removedItems('floppies')"
              :key="`removed-${floppy}`"
              class="flex items-center gap-2"
            >
              <Icon name="save-01" size="sm" stroke-color="gray-warm-400" />
              <SummaryValue :value="floppy" removed />
            </div>
          </div>
        </div>

        <!-- Reservables -->
        <div v-if="hasReservables" class="flex flex-col gap-4">
          <div class="flex items-center gap-2.5">
            <div class="text-sm font-bold text-gray-warm-500">
              {{ t('components.domain-hardware-summary.reservables.title') }}
            </div>
            <Separator class="flex-1" />
          </div>
          <div v-if="props.vgpus" class="flex flex-wrap items-center gap-x-4 gap-y-3">
            <Icon name="gpu" size="md" stroke-color="gray-warm-700" />
            <SummaryValue v-bind="field('vgpus', list)" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
