<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'

import { getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Icon } from '@/components/icon'
import { CopyIcon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()

interface Props {
  desktopId: string
  desktopStatus?: string
  // Top-level desktop IP (the WireGuard guest IP when wireguard is attached
  // and the desktop is Started — apiv4 only exposes per-interface IP for
  // wireguard so we render it inline with the wireguard row).
  desktopIp?: string | null
  fullHeight?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  desktopStatus: undefined,
  desktopIp: undefined,
  fullHeight: true
})

const emit = defineEmits<{
  showNetworksModal: []
}>()

const {
  isPending: networksIsPending,
  isError: networksIsError,
  error: networksError,
  data: networks
} = useQuery(
  getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions({
    path: {
      desktop_id: props.desktopId
    }
  })
)

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
</script>

<template>
  <div v-if="networksIsPending" class="grid grid-cols-2 gap-x-3 gap-y-1.5">
    <Skeleton class="bg-base-white/20 h-9" />
    <Skeleton class="bg-base-white/20 h-9" />
    <Skeleton v-if="props.fullHeight" class="bg-base-white/20 h-9" />
  </div>

  <div v-else-if="networksIsError" class="flex items-center gap-2 py-2 text-base-white/90">
    <Icon name="alert-circle" size="sm" stroke-color="error-300" />
    <span class="text-xs">
      {{ networksError?.message || t('components.desktop-networks-modal.error') }}
    </span>
  </div>

  <div v-else-if="!sortedNetworks.length" class="flex items-center gap-2 py-2 text-base-white/80">
    <Icon name="alert-circle" size="sm" stroke-color="warning-300" />
    <span class="text-xs">{{ t('components.desktop-networks-modal.empty') }}</span>
  </div>

  <div v-else class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-start text-base-white">
    <div v-for="network in visibleNetworks" :key="network.id" class="flex flex-col min-w-0">
      <div class="text-xs font-semibold truncate">{{ network.name }}</div>
      <div class="text-[11px] text-base-white/80 truncate flex items-center gap-1.5 font-mono">
        {{ network.mac
        }}<CopyIcon :value="network.mac" class="opacity-80" size="xs" stroke-color="base-white" />
      </div>
      <!-- Wireguard-only: IP attached as a sub-row so it's clearly the IP
           you reach this interface on — not a free-floating top-of-card
           field that's easy to miss. -->
      <div
        v-if="network.id === 'wireguard'"
        class="text-[11px] text-base-white/80 truncate flex items-center gap-1.5 font-mono"
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

    <!-- Overflow → opens the full modal which lists every interface in detail -->
    <div v-if="overflowCount > 0" class="flex items-center justify-end col-span-2">
      <Button
        variant="ghost"
        class="h-6 px-2 bg-base-white/15 hover:bg-base-white/30 text-[11px] font-semibold text-base-white"
        @click="emit('showNetworksModal')"
      >
        +{{ overflowCount }} {{ t('components.desktops.desktop-card.networks.more') }}
      </Button>
    </div>
  </div>
</template>
