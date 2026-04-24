<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { getDesktopNetworksOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Icon, CopyIcon } from '@/components/icon'
import { Label } from '@/components/ui/label'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopId: string
  desktopName: string
  // The top-level desktop IP — used as the wireguard guest IP when present.
  desktopIp?: string | null
  desktopStatus?: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  desktopIp: undefined,
  desktopStatus: undefined
})

const emit = defineEmits<{ close: [] }>()

const {
  data: desktopNetworks,
  isPending,
  isError,
  error
} = useQuery(
  getDesktopNetworksOptions({
    path: {
      desktop_id: props.desktopId
    }
  })
)

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
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    size="2xl"
    class="pt-6"
    :title="t('components.desktop-networks-modal.title', { name: props.desktopName })"
    :description="t('components.desktop-networks-modal.description')"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-3 pb-4">
      <div
        v-if="isPending"
        class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
      >
        <Skeleton class="h-6 w-48" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-9 w-3/4" />
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
        v-else-if="!sortedNetworks.length"
        class="bg-base-white p-6 rounded-lg border border-gray-warm-300 flex flex-col items-center text-center gap-2"
      >
        <Icon name="modem-02" size="lg" stroke-color="gray-warm-400" />
        <p class="font-semibold text-gray-warm-700">
          {{ t('components.desktop-networks-modal.empty') }}
        </p>
      </div>

      <section
        v-for="network in sortedNetworks"
        v-else
        :key="network.id"
        class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
      >
        <div class="flex items-center gap-2">
          <Icon :name="interfaceIcon(network.id)" size="md" stroke-color="gray-warm-700" />
          <h3 class="font-semibold text-gray-warm-700 truncate">{{ network.name }}</h3>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-2 text-sm">
          <div class="flex flex-col gap-1 min-w-0">
            <Label class="text-xs uppercase tracking-wide text-gray-warm-500">
              {{ t('components.desktop-networks-modal.fields.id') }}
            </Label>
            <div class="flex items-center gap-2 min-w-0">
              <code
                class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-1 truncate flex-1"
              >
                {{ network.id }}
              </code>
              <CopyIcon :value="network.id" size="sm" stroke-color="gray-warm-600" />
            </div>
          </div>

          <div class="flex flex-col gap-1 min-w-0">
            <Label class="text-xs uppercase tracking-wide text-gray-warm-500">
              {{ t('components.desktop-networks-modal.fields.mac') }}
            </Label>
            <div class="flex items-center gap-2 min-w-0">
              <code
                class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-1 truncate flex-1"
              >
                {{ network.mac }}
              </code>
              <CopyIcon :value="network.mac" size="sm" stroke-color="gray-warm-600" />
            </div>
          </div>

          <div v-if="network.id === 'wireguard'" class="flex flex-col gap-1 min-w-0">
            <Label class="text-xs uppercase tracking-wide text-gray-warm-500">
              {{ t('components.desktop-networks-modal.fields.ip') }}
            </Label>
            <div class="flex items-center gap-2 min-w-0">
              <template v-if="props.desktopStatus === DesktopStatusEnum.WAITING_IP">
                <Icon
                  name="loading-02"
                  size="sm"
                  class="animate-spin"
                  stroke-color="gray-warm-600"
                />
                <span class="text-xs italic text-gray-warm-600">
                  {{ t('components.desktops.desktop-card.status.waitingip.text') }}
                </span>
              </template>
              <template v-else-if="props.desktopIp">
                <code
                  class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-1 truncate flex-1"
                >
                  {{ props.desktopIp }}
                </code>
                <CopyIcon :value="props.desktopIp" size="sm" stroke-color="gray-warm-600" />
              </template>
              <span v-else class="text-xs italic text-gray-warm-500">
                {{ t('components.desktop-networks-modal.no-ip') }}
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </Modal>
</template>
