<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { useEventListener, useMediaQuery } from '@vueuse/core'

import {
  getDesktopNetworksOptions,
  getNetworksFromTokenOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum, type DesktopNetwork } from '@/gen/oas/apiv4'
import type { Client } from '@/gen/oas/apiv4/client'

import { Icon, CopyIcon } from '@/components/icon'
import { Modal } from '@/components/modal'
import { TruncatedText } from '@/components/truncated-text'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger
} from '@/components/ui/context-menu'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { domainKindStyle, resolveDomainKind, type DesktopKind } from '@/lib/domainKind'
import { copyToClipboard } from '@/lib/utils'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopId: string
  desktopName: string
  // The top-level desktop IP. Used as the wireguard guest IP when present.
  desktopIp?: string | null
  desktopStatus?: string
  desktopKind?: DesktopKind | null
  // When provided, fetches networks via the direct-viewer token endpoint
  // (using the supplied client's viewer JWT) instead of the standard
  // user-authenticated endpoint keyed by desktopId.
  directViewerToken?: string
  directViewerClient?: Client
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  desktopIp: undefined,
  desktopStatus: undefined,
  desktopKind: undefined,
  directViewerToken: undefined,
  directViewerClient: undefined
})

const emit = defineEmits<{ close: [] }>()

const tokenNetworksQueryOptions = {
  ...getNetworksFromTokenOptions({
    path: { token: props.directViewerToken ?? '' },
    client: props.directViewerClient
  }),
  enabled: !!props.directViewerToken && !!props.directViewerClient
}

const desktopIdNetworksQueryOptions = {
  ...getDesktopNetworksOptions({
    path: { desktop_id: props.desktopId }
  }),
  enabled: !props.directViewerToken
}

const tokenQuery = useQuery(tokenNetworksQueryOptions)
const desktopIdQuery = useQuery(desktopIdNetworksQueryOptions)

const active = computed(() => (props.directViewerToken ? tokenQuery : desktopIdQuery))
const isPending = computed(() => active.value.isPending.value)
const isError = computed(() => active.value.isError.value)
const error = computed(() => active.value.error.value)
const desktopNetworks = computed(() => active.value.data.value)

// Wireguard first so users see the routable IP at a glance.
const sortedNetworks = computed(() => {
  const list = desktopNetworks.value?.networks ?? []
  return [...list].sort((a, b) => {
    if (a.id === 'wireguard') return -1
    if (b.id === 'wireguard') return 1
    return 0
  })
})

const interfaceIcon = (id: string) => {
  if (id === 'wireguard') return 'globe-04'
  if (id.startsWith('private') || id === 'personal') return 'lock-04'
  if (id.includes('shared')) return 'share-04'
  return 'modem-02'
}

const wantedColumns = computed(() => {
  const count = sortedNetworks.value.length
  if (count > 15) return 3
  if (count > 5) return 2
  return 1
})

const fitsTwoColumns = useMediaQuery('(min-width: 768px)')
const fitsThreeColumns = useMediaQuery('(min-width: 1024px)')
const columns = computed(() =>
  Math.min(wantedColumns.value, fitsThreeColumns.value ? 3 : fitsTwoColumns.value ? 2 : 1)
)

const gridColumnsClass = computed(
  () => ['grid-cols-1', 'grid-cols-2', 'grid-cols-3'][columns.value - 1]
)

const modalSize = computed(() => (['2xl', '4xl', '6xl'] as const)[wantedColumns.value - 1])

const lastRowStart = computed(
  () => Math.floor((sortedNetworks.value.length - 1) / columns.value) * columns.value
)

const fillerCount = computed(() => {
  const remainder = sortedNetworks.value.length % columns.value
  return remainder === 0 ? 0 : columns.value - remainder
})

const sectionClass = (index: number) => [
  index >= columns.value ? 'border-t border-gray-warm-200 pt-3' : 'pt-1.5',
  index >= lastRowStart.value ? 'pb-0' : 'pb-3',
  index % columns.value !== 0
    ? 'relative pl-4 before:absolute before:inset-y-3 before:left-0 before:w-px before:bg-gray-warm-200'
    : '',
  (index + 1) % columns.value !== 0 ? 'pr-4' : ''
]

const kindStyle = computed(() => domainKindStyle(resolveDomainKind('desktop', props.desktopKind)))

const kindLabel = computed(() =>
  t(`components.domain-info-modal.kind.${props.desktopKind ?? 'desktop'}`)
)

const showIds = ref(false)
useEventListener(window, 'keydown', (event: KeyboardEvent) => {
  if (event.ctrlKey && event.altKey && event.key.toLowerCase() === 'i') {
    showIds.value = !showIds.value
  }
})

const copyableFields = (network: DesktopNetwork) => {
  const fields = showIds.value
    ? [{ key: 'id', label: t('components.desktop-networks-modal.fields.id'), value: network.id }]
    : []
  fields.push({
    key: 'mac',
    label: t('components.desktop-networks-modal.fields.mac'),
    value: network.mac
  })
  return fields
}

const closeModal = () => {
  showIds.value = false
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    :size="modalSize"
    :title="t('components.desktop-networks-modal.title')"
    @close="closeModal()"
  >
    <div class="flex flex-col gap-6">
      <div
        v-if="isPending"
        class="bg-base-white p-3 rounded-lg border border-gray-warm-300"
        role="status"
        aria-busy="true"
      >
        <span class="sr-only">{{ t('components.desktop-networks-modal.loading') }}</span>
        <div class="flex items-center pb-2" aria-hidden="true">
          <Skeleton class="h-7 w-40" />
        </div>
        <Separator class="my-1.5" />
        <div class="flex flex-col gap-3 pt-1" aria-hidden="true">
          <Skeleton class="h-4 w-28" />
          <Skeleton class="h-8 w-56" />
          <Skeleton class="h-4 w-24" />
          <Skeleton class="h-8 w-56" />
        </div>
      </div>

      <div
        v-else-if="isError"
        class="bg-error-25 border border-error-300 rounded-lg p-5 flex items-start gap-3"
      >
        <Icon name="alert-circle" size="md" stroke-color="error-700" />
        <div>
          <p class="font-semibold text-error-700">
            {{ t('components.desktop-networks-modal.error') }}
          </p>
          <p class="text-sm text-error-700/90">
            {{ error?.message || 'Unknown error' }}
          </p>
        </div>
      </div>

      <div
        v-else
        class="bg-base-white py-5 px-4 rounded-lg border border-gray-warm-300"
        :class="kindStyle.accent"
      >
        <div class="flex items-center pb-2">
          <h3
            class="flex flex-wrap items-baseline gap-x-1.5 px-1.5 rounded-xs font-semibold text-md min-w-0"
            :class="kindStyle.badge"
          >
            <span class="shrink-0 text-sm font-regular">{{ kindLabel }}</span>
            <span class="min-w-0 break-words">{{ props.desktopName }}</span>
          </h3>
        </div>
        <Separator class="my-1.5" />

        <div class="flex flex-col gap-3 text-gray-warm-700">
          <Empty v-if="!sortedNetworks.length" class="p-6">
            <EmptyHeader class="gap-1.5">
              <EmptyMedia variant="icon">
                <Icon name="modem-02" />
              </EmptyMedia>
              <EmptyTitle class="text-sm font-medium">
                {{ t('components.desktop-networks-modal.empty') }}
              </EmptyTitle>
            </EmptyHeader>
          </Empty>

          <div v-else class="grid" :class="gridColumnsClass">
            <section
              v-for="(network, index) in sortedNetworks"
              :key="network.id"
              class="flex flex-col gap-1.5"
              :class="sectionClass(index)"
            >
              <div class="flex items-center gap-1.5">
                <ContextMenu>
                  <ContextMenuTrigger>
                    <span class="flex shrink-0">
                      <Icon :name="interfaceIcon(network.id)" size="md" stroke-color="brand-700" />
                    </span>
                  </ContextMenuTrigger>
                  <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
                    <ContextMenuItem @click="copyToClipboard(network.id)">
                      {{ t('components.desktop-networks-modal.debug-options.copy-id') }}
                    </ContextMenuItem>
                  </ContextMenuContent>
                </ContextMenu>
                <TruncatedText
                  as="h4"
                  :title="network.name"
                  class="min-w-0 text-xs font-bold text-brand-700 uppercase tracking-wide"
                />
              </div>

              <dl class="grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-2">
                <template v-for="field in copyableFields(network)" :key="field.key">
                  <dt class="text-xs font-medium text-brand-600 uppercase tracking-wide">
                    {{ field.label }}
                  </dt>
                  <dd
                    class="m-0 min-w-0 max-w-fit flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 text-sm font-regular"
                    :class="kindStyle.tint"
                  >
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <span
                          tabindex="0"
                          class="truncate min-w-0 rounded-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          >{{ field.value }}</span
                        >
                      </TooltipTrigger>
                      <TooltipContent :title="field.value" side="top" />
                    </Tooltip>
                    <CopyIcon :value="field.value" size="md" stroke-color="gray-warm-600" />
                  </dd>
                </template>

                <template v-if="network.id === 'wireguard'">
                  <dt
                    class="self-center text-xs font-medium text-brand-600 uppercase tracking-wide"
                  >
                    {{ t('components.desktop-networks-modal.fields.ip') }}
                  </dt>
                  <dd
                    v-if="props.desktopStatus === DesktopStatusEnum.WAITING_IP"
                    class="m-0 min-w-0 self-center flex items-center gap-1.5 text-sm font-regular italic text-gray-warm-600"
                  >
                    <Icon
                      name="loading-02"
                      size="sm"
                      class="animate-spin"
                      stroke-color="gray-warm-600"
                    />
                    {{ t('components.desktops.desktop-card.status.waitingip.text') }}
                  </dd>
                  <dd
                    v-else-if="props.desktopIp"
                    class="m-0 min-w-0 max-w-fit flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 text-sm font-regular"
                    :class="kindStyle.tint"
                  >
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <span
                          tabindex="0"
                          class="truncate min-w-0 rounded-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          >{{ props.desktopIp }}</span
                        >
                      </TooltipTrigger>
                      <TooltipContent :title="props.desktopIp" side="top" />
                    </Tooltip>
                    <CopyIcon :value="props.desktopIp" size="md" stroke-color="gray-warm-600" />
                  </dd>
                  <dd
                    v-else
                    class="m-0 min-w-0 self-center text-sm font-regular italic text-gray-warm-500"
                  >
                    {{ t('components.desktop-networks-modal.no-ip') }}
                  </dd>
                </template>
              </dl>
            </section>

            <div
              v-for="filler in fillerCount"
              :key="`filler-${filler}`"
              aria-hidden="true"
              :class="sectionClass(sortedNetworks.length + filler - 1)"
            />
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
