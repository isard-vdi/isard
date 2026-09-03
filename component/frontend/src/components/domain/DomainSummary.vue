<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { useI18n } from 'vue-i18n'
import SummaryRow from '@/components/domain/SummaryRow.vue'
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

const NO_VALUE = '—'

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
  return {
    value: format(props[key]),
    state: changed ? ('changed' as const) : undefined,
    previous: changed ? format(before) : null
  }
}

function credential(name: 'username' | 'password') {
  const current = props.credentials?.[name] ?? ''
  const before = props.previous?.credentials?.[name]
  if (before === undefined || (before ?? '') === current) return { value: current || NO_VALUE }
  if (!before) return { value: current, state: 'added' as const }
  return { value: current || NO_VALUE, state: 'changed' as const, previous: before }
}

const credentialFields = computed(() => ({
  username: credential('username'),
  password: credential('password')
}))

type ListKey = 'interfaces' | 'isos' | 'floppies'

// Items are matched by membership, not by position: a reorder is not a change.
const listItem = (key: ListKey, item: string) => {
  const before = props.previous?.[key]
  const added = before !== undefined && !before.includes(item)
  return { value: item, state: added ? ('added' as const) : undefined }
}

/** What the field held before the edits and no longer does. */
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
const vcpuLabel = (vcpu?: number) =>
  t('components.domain-info-modal.fields.hardware.vcpu', { vcpu })
const memoryLabel = (memory?: number) =>
  t('components.domain-info-modal.fields.hardware.ram', { ram: memory?.toFixed(2) })
const diskSizeLabel = (size?: number) => `${size} ${t('common.units.gb')}`

// Credentials only make sense for the viewers that go through Wireguard; the
// rest never surface them, so showing them there would be misleading.
const showCredentials = computed(() => {
  if (!hasWireguardRequiringViewer(props.viewers ?? [])) return false
  const { username, password } = credentialFields.value
  return !!(
    props.credentials?.username ||
    props.credentials?.password ||
    username.state ||
    password.state
  )
})

const hasViewers = computed(() => Boolean(props.viewers && props.viewers.length > 0))

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

const removedVgpus = computed(() =>
  props.vgpus?.length ? [] : (props.previous?.vgpus ?? []).filter(Boolean)
)

const hasReservables = computed(
  () => Boolean(props.vgpus && props.vgpus.length > 0) || removedVgpus.value.length > 0
)
</script>

<template>
  <div
    :class="
      cn('bg-base-white px-4 py-2 rounded-md border border-gray-warm-200', accent, props.class)
    "
  >
    <h2 v-if="props.title" class="py-2 text-lg font-bold text-gray-warm-700">{{ props.title }}</h2>

    <div class="flex flex-col divide-y divide-gray-warm-200">
      <template v-if="props.loading">
        <SummaryRow v-for="row in 4" :key="row" loading />
      </template>

      <template v-else>
        <!-- Viewers -->
        <SummaryRow
          v-if="hasViewers"
          icon="monitor"
          :label="t('components.domain-access-summary.viewers.title')"
        >
          <SummaryValue icon="expand-06" v-bind="field('fullscreen', fullscreenLabel)" />
          <SummaryValue icon="monitor" v-bind="field('viewers', viewerLabels)" />
        </SummaryRow>

        <!-- Credentials -->
        <SummaryRow
          v-if="showCredentials"
          icon="user-03"
          :label="t('components.domain-access-summary.credentials.title')"
        >
          <SummaryValue
            icon="user-03"
            v-bind="credentialFields.username"
            :label="t('components.domain-summary.tags.user')"
            truncate
          />
          <SummaryValue
            icon="passcode-lock"
            v-bind="credentialFields.password"
            :label="t('components.domain-summary.tags.password')"
            truncate
          />
        </SummaryRow>

        <!-- System -->
        <SummaryRow
          v-if="hasSystemInfo"
          icon="cpu"
          :label="t('components.domain-hardware-summary.system.title')"
        >
          <SummaryValue v-if="props.vcpu" icon="cpu" v-bind="field('vcpu', vcpuLabel)" />
          <SummaryValue v-if="props.memory" icon="memory" v-bind="field('memory', memoryLabel)" />
          <SummaryValue
            v-if="props.diskSize"
            icon="hdd"
            v-bind="field('diskSize', diskSizeLabel)"
            :label="t('components.domain-summary.tags.disk')"
          />
          <SummaryValue
            v-if="props.diskBus"
            icon="hdd-02"
            v-bind="field('diskBus', text)"
            :label="t('components.domain-summary.tags.disk-bus')"
          />
          <SummaryValue
            v-if="props.videos"
            icon="wires"
            v-bind="field('videos', list)"
            :label="t('components.domain-summary.tags.video')"
          />
          <SummaryValue
            v-if="props.bootOrder"
            icon="hdd"
            v-bind="field('bootOrder', list)"
            :label="t('components.domain-summary.tags.boot')"
          />
        </SummaryRow>

        <!-- Peripherals -->
        <SummaryRow
          v-if="hasPeripherals"
          icon="disc-02"
          :label="t('components.domain-hardware-summary.peripherals.title')"
        >
          <SummaryValue
            v-for="(iso, index) in props.isos"
            :key="`iso-${index}`"
            icon="disc-02"
            v-bind="listItem('isos', iso)"
            :label="t('components.domain-summary.tags.iso')"
          />
          <SummaryValue
            v-for="(iso, index) in removedItems('isos')"
            :key="`iso-removed-${index}`"
            icon="disc-02"
            :value="iso"
            state="removed"
            :label="t('components.domain-summary.tags.iso')"
          />
          <SummaryValue
            v-for="(floppy, index) in props.floppies"
            :key="`floppy-${index}`"
            icon="save-01"
            v-bind="listItem('floppies', floppy)"
            :label="t('components.domain-summary.tags.floppy')"
          />
          <SummaryValue
            v-for="(floppy, index) in removedItems('floppies')"
            :key="`floppy-removed-${index}`"
            icon="save-01"
            :value="floppy"
            state="removed"
            :label="t('components.domain-summary.tags.floppy')"
          />
        </SummaryRow>

        <!-- Reservables -->
        <SummaryRow
          v-if="hasReservables"
          icon="gpu"
          :label="t('components.domain-hardware-summary.reservables.title')"
        >
          <SummaryValue v-if="props.vgpus?.length" icon="gpu" v-bind="field('vgpus', list)" />
          <SummaryValue v-else icon="gpu" :value="list(removedVgpus)" state="removed" />
        </SummaryRow>

        <!-- Networks -->
        <SummaryRow
          v-if="hasNetworks"
          icon="modem-02"
          :label="t('components.domain-hardware-summary.networks.title')"
        >
          <!-- Numbered: the order the interfaces sit in is what the domain gets. -->
          <SummaryValue
            v-for="(network, index) in props.interfaces"
            :key="`interface-${index}`"
            v-bind="listItem('interfaces', network)"
            :label="`${index + 1}.`"
          />
          <!-- A dropped interface has no position left to number. -->
          <SummaryValue
            v-for="(network, index) in removedItems('interfaces')"
            :key="`interface-removed-${index}`"
            :value="network"
            state="removed"
          />
        </SummaryRow>
      </template>
    </div>
  </div>
</template>
