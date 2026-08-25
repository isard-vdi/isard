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
// Both groups follow the order the forms below the card lay their inputs out.
export interface DomainSummaryData {
  // Access
  fullscreen?: boolean
  viewers?: string[]
  // Nullable fields: that is what the generated domain/template responses carry.
  credentials?: {
    username?: string | null
    password?: string | null
  } | null
  // bastion?:
  // Hardware
  vcpu?: number
  memory?: number
  diskSize?: number
  diskBus?: string
  videos?: string[]
  bootOrder?: string[]
  isos?: string[]
  floppies?: string[]
  vgpus?: string[] | null
  interfaces?: string[]
}

export type DomainSummaryKind = 'persistent' | 'nonpersistent' | 'deployment' | 'template'

interface Props extends DomainSummaryData {
  // Card
  title?: string
  loading?: boolean
  kind?: DomainSummaryKind
  /** What the fields held before the edits, when the card tracks live forms. */
  previous?: DomainSummaryData
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  viewers: undefined,
  credentials: undefined,
  vcpu: undefined,
  memory: undefined,
  diskSize: undefined,
  diskBus: undefined,
  videos: undefined,
  bootOrder: undefined,
  isos: undefined,
  floppies: undefined,
  vgpus: undefined,
  interfaces: undefined,
  title: undefined,
  kind: undefined,
  previous: undefined,
  class: undefined
})

const { t } = useI18n()

const accent = computed(() => {
  switch (props.kind) {
    case 'nonpersistent':
      return 'border-l-6 border-l-secondary-1-500'
    case 'deployment':
      return 'border-l-6 border-l-secondary-2-500'
    case 'persistent':
      return 'border-l-6 border-l-secondary-3-500'
    case 'template':
      return 'border-l-6 border-l-brand-700'
    default:
      return ''
  }
})

const sameValue = (a: unknown, b: unknown) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** Renders a value, flagged when its field has moved since the edits started. */
function field<K extends keyof DomainSummaryData>(
  key: K,
  format: (value: DomainSummaryData[K]) => string
) {
  const before = props.previous?.[key]
  // A baseline that has not seeded itself is missing, not empty.
  return {
    value: format(props[key]),
    changed: before !== undefined && !sameValue(props[key], before)
  }
}

function credential(name: 'username' | 'password') {
  const current = props.credentials?.[name] ?? ''
  const before = props.previous?.credentials?.[name]
  return { value: current, changed: before !== undefined && before !== current }
}

type ListKey = 'interfaces' | 'isos' | 'floppies'

const listItem = (key: ListKey, item: string) => {
  const before = props.previous?.[key]
  return { value: item, changed: before !== undefined && !before.includes(item) }
}

const iconColor = (changed: boolean) => (changed ? 'brand-700' : 'gray-warm-700')

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

const hasNetworks = computed(() => Boolean(props.interfaces?.length))

const hasPeripherals = computed(() => Boolean(props.isos?.length || props.floppies?.length))

const hasReservables = computed(() => Boolean(props.vgpus && props.vgpus.length > 0))

const hasHardwareInfo = computed(() => {
  return hasSystemInfo.value || hasNetworks.value || hasPeripherals.value || hasReservables.value
})
</script>

<template>
  <div
    :class="
      cn('bg-gray-warm-50 px-4 py-2 rounded-md border border-gray-warm-200', accent, props.class)
    "
  >
    <h2 v-if="props.title" class="py-2 text-lg font-bold text-gray-warm-700">{{ props.title }}</h2>

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
            <SummaryValue v-slot="{ changed }" v-bind="field('fullscreen', fullscreenLabel)">
              <Icon name="expand-06" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue v-slot="{ changed }" v-bind="field('viewers', viewerLabels)">
              <Icon name="monitor" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
          </div>
        </div>
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
            <SummaryValue
              v-if="props.credentials?.username"
              v-slot="{ changed }"
              v-bind="credential('username')"
            >
              <Icon name="user-03" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue
              v-if="props.credentials?.password"
              v-slot="{ changed }"
              v-bind="credential('password')"
            >
              <Icon name="passcode-lock" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
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
            <SummaryValue v-if="props.vcpu" v-slot="{ changed }" v-bind="field('vcpu', vcpuLabel)">
              <Icon name="cpu" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue
              v-if="props.memory"
              v-slot="{ changed }"
              v-bind="field('memory', memoryLabel)"
            >
              <Icon name="memory" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue
              v-if="props.diskSize"
              v-slot="{ changed }"
              v-bind="field('diskSize', diskSizeLabel)"
            >
              <Icon name="hdd" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue v-if="props.diskBus" v-slot="{ changed }" v-bind="field('diskBus', text)">
              <Icon name="hdd-02" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue v-if="props.videos" v-slot="{ changed }" v-bind="field('videos', list)">
              <Icon name="wires" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue
              v-if="props.bootOrder"
              v-slot="{ changed }"
              v-bind="field('bootOrder', list)"
            >
              <Icon name="hdd" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
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
            <SummaryValue
              v-for="iso in props.isos"
              :key="iso"
              v-bind="listItem('isos', iso)"
              v-slot="{ changed }"
            >
              <Icon name="disc-02" size="sm" :stroke-color="iconColor(changed)" />
            </SummaryValue>
            <SummaryValue
              v-for="floppy in props.floppies"
              :key="floppy"
              v-bind="listItem('floppies', floppy)"
              v-slot="{ changed }"
            >
              <Icon name="save-01" size="sm" :stroke-color="iconColor(changed)" />
            </SummaryValue>
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
            <SummaryValue v-slot="{ changed }" v-bind="field('vgpus', list)">
              <Icon name="gpu" size="md" :stroke-color="iconColor(changed)" />
            </SummaryValue>
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
            <SummaryValue
              v-for="network in props.interfaces"
              :key="network"
              v-bind="listItem('interfaces', network)"
            />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
