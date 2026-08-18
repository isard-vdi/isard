<script setup lang="ts">
import { computed, inject } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'

import {
  getDesktopNetworksOptions,
  getNetworksFromTokenOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import type { Client } from '@/gen/oas/apiv4/client'

import { Icon } from '@/components/icon'
import { CopyIcon } from '@/components/icon'
import { TruncatedText } from '@/components/truncated-text'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { CARD_SIZE_INJECTION_KEY, cardOverlayTextVariants, cardOverlayDetailVariants } from '..'

const { t } = useI18n()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

interface Props {
  desktopId: string
  desktopStatus?: string
  // Top-level desktop IP (the WireGuard guest IP when wireguard is attached
  // and the desktop is Started — apiv4 only exposes per-interface IP for
  // wireguard so we render it inline with the wireguard row).
  desktopIp?: string | null
  fullHeight?: boolean
  // When provided, fetches networks via the direct-viewer token endpoint
  // (using the supplied client's viewer JWT). Otherwise falls back to the
  // standard user-authenticated endpoint keyed by desktopId.
  directViewerToken?: string
  directViewerClient?: Client
}

const props = withDefaults(defineProps<Props>(), {
  desktopStatus: undefined,
  desktopIp: undefined,
  fullHeight: true,
  directViewerToken: undefined,
  directViewerClient: undefined
})

const emit = defineEmits<{
  showNetworksModal: []
}>()

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
const networksIsPending = computed(() => active.value.isPending.value)
const networksIsError = computed(() => active.value.isError.value)
const networksError = computed(() => active.value.error.value)
const networks = computed(() => active.value.data.value)

// Wireguard ALWAYS shown first when present so users with many networks
// still see the IP at a glance — the +N overflow then covers the rest.
const sortedNetworks = computed(() => {
  const list = networks.value?.networks ?? []
  return [...list].sort((a, b) => {
    if (a.id === 'wireguard') return -1
    if (b.id === 'wireguard') return 1
    return 0
  })
})

const visibleLimit = computed(() => (props.fullHeight ? 4 : 2))
const visibleNetworks = computed(() => sortedNetworks.value.slice(0, visibleLimit.value))
const overflowCount = computed(() => Math.max(0, sortedNetworks.value.length - visibleLimit.value))

// Exposed so the parent card can drop its own expand button when the +N
// overflow button already opens the modal — otherwise both show at once.
defineExpose({ hasOverflow: computed(() => overflowCount.value > 0) })
</script>

<template>
  <div v-if="networksIsPending" class="grid grid-cols-2 gap-x-3 gap-y-1.5">
    <Skeleton class="bg-base-white/20 h-9" />
    <Skeleton class="bg-base-white/20 h-9" />
    <Skeleton v-if="props.fullHeight" class="bg-base-white/20 h-9" />
  </div>

  <div v-else-if="networksIsError" class="flex items-center gap-2 py-2 text-base-white/90">
    <Icon name="alert-circle" size="sm" stroke-color="error-300" />
    <span :class="cardOverlayTextVariants({ size })">
      {{ networksError?.message || t('components.desktop-networks-modal.error') }}
    </span>
  </div>

  <div v-else-if="!sortedNetworks.length" class="flex items-center gap-2 py-2 text-base-white/80">
    <Icon name="alert-circle" size="sm" stroke-color="warning-300" />
    <span :class="cardOverlayTextVariants({ size })">{{
      t('components.desktop-networks-modal.empty')
    }}</span>
  </div>

  <div v-else class="flex gap-3 text-start text-base-white">
    <div class="grid grid-cols-2 gap-x-3 gap-y-1.5 flex-1 min-w-0">
      <div v-for="network in visibleNetworks" :key="network.id" class="flex flex-col min-w-0">
        <TruncatedText
          :title="network.name"
          class="font-semibold"
          :class="cardOverlayTextVariants({ size })"
        />
        <div
          class="text-base-white/80 flex items-center gap-1.5 font-mono min-w-0"
          :class="cardOverlayDetailVariants({ size })"
        >
          <TruncatedText :title="network.mac" class="min-w-0" />
          <CopyIcon :value="network.mac" class="opacity-80" size="xs" stroke-color="base-white" />
        </div>
        <!-- Wireguard-only: IP attached as a sub-row so it's clearly the IP
             you reach this interface on — not a free-floating top-of-card
             field that's easy to miss. -->
        <div
          v-if="network.id === 'wireguard'"
          class="text-base-white/80 truncate flex items-center gap-1.5 font-mono"
          :class="cardOverlayDetailVariants({ size })"
        >
          <template v-if="props.desktopStatus === DesktopStatusEnum.WAITING_IP">
            <Icon name="loading-02" size="xs" class="animate-spin" stroke-color="base-white" />
            <span class="italic">
              {{ t('components.desktops.desktop-card.status.waitingip.text') }}
            </span>
          </template>
          <template v-else-if="props.desktopIp">
            {{ props.desktopIp }}
            <CopyIcon
              :value="props.desktopIp"
              class="opacity-80"
              size="xs"
              stroke-color="base-white"
            />
          </template>
          <span v-else class="italic text-base-white/50">—</span>
        </div>
      </div>
    </div>

    <!-- Overflow → occupies a narrow column beside the networks; the button
         itself stays compact (bottom-aligned, background only around its
         content) and opens the modal. -->
    <div v-if="overflowCount > 0" class="self-stretch shrink-0 flex items-end">
      <Button
        variant="ghost"
        class="h-auto flex items-center justify-center gap-1 px-2 py-1 rounded-md bg-base-white/15 hover:bg-base-white/30 font-semibold whitespace-nowrap text-base-white"
        :class="cardOverlayDetailVariants({ size })"
        @click="emit('showNetworksModal')"
      >
        +{{ overflowCount }} {{ t('components.desktops.desktop-card.networks.more')
        }}<Icon name="chevron-right" size="xs" stroke-color="base-white" />
      </Button>
    </div>
  </div>
</template>
