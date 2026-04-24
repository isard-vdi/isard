<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Icon, CopyIcon } from '@/components/icon'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopId: string
  desktopName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const {
  data: desktopNetworks,
  isPending: desktopNetworksIsPending,
  isError: DesktopNetworksIsError,
  error: DesktopNetworksError
} = useQuery(
  getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions({
    path: {
      desktop_id: props.desktopId
    }
  })
)
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    class="pt-4 pb-1"
    :title="t('components.desktop-networks-modal.title', { name: props.desktopName })"
    size="xl"
    @close="emit('close')"
  >
    <div v-if="desktopNetworksIsPending" class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Skeleton class="bg-gray-warm-600 h-9" />
      <Skeleton class="bg-gray-warm-600 h-9" />
      <Skeleton class="bg-gray-warm-600 h-9" />
    </div>
    <div v-else-if="DesktopNetworksIsError">
      <div class="flex flex-col items-center justify-center py-4">
        <div class="text-center">
          <p class="flex items-center justify-center text-error-700 font-semibold gap-2 text-lg">
            <Icon name="alert-circle" size="md" stroke-color="error-700" />
            Error loading networks:
          </p>
          <div class="text-error-500 text-md mt-1">
            {{ DesktopNetworksError?.message || t('api.errors.unknown') }}
          </div>
        </div>
      </div>
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4 w-120">
      <div v-for="network in desktopNetworks?.networks" :key="network.id" class="flex flex-col">
        <div class="text-md font-semibold truncate">{{ network.name }}</div>
        <div class="truncate flex items-center gap-2 font-mono">
          {{ network.mac
          }}<CopyIcon
            :value="network.mac"
            class="opacity-80"
            size="sm"
            stroke-color="gray-warm-800"
          />
        </div>
      </div>
    </div>
  </Modal>
</template>
