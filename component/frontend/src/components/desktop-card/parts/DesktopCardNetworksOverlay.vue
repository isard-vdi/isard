<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'

import { getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Icon } from '@/components/icon'
import { CopyIcon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

interface Props {
  desktopId: string
  fullHeight?: boolean
}

const props = withDefaults(defineProps<Props>(), {
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
</script>

<template>
  <div v-if="networksIsPending" class="grid grid-cols-2 gap-4">
    <Skeleton class="bg-gray-warm-600 h-9" />
    <Skeleton class="bg-gray-warm-600 h-9" />
    <Skeleton v-if="props.fullHeight" class="bg-gray-warm-600 h-9" />
  </div>
  <div v-else-if="networksIsError" class="flex flex-col items-center justify-center py-4">
    <Icon name="alert-circle" class="w-5 h-5 text-red-500 mb-2" />
    <div class="text-white text-center">
      Error loading networks:
      <div class="text-red-400 text-xs mt-1">
        {{ networksError?.message || 'Unknown error' }}
      </div>
    </div>
  </div>
  <div
    v-else-if="!networks?.networks?.length"
    class="flex flex-col items-center justify-center py-4 text-amber-400"
  >
    <Icon name="alert-circle" class="w-5 h-5 text-red-500 mb-2" />
    <span class="text-white">No networks available</span>
  </div>
  <template v-else>
    <div class="grid grid-cols-2 gap-4 text-start">
      <div
        v-for="(network, index) in networks.networks.slice(0, props.fullHeight ? 4 : 2)"
        :key="index"
        class="flex flex-row items-center justify-between"
      >
        <div class="text-white flex flex-col">
          <div class="text-xs font-semibold truncate">{{ network.name }}</div>
          <div class="text-xs text-white/80 truncate flex items-center gap-2 font-mono">
            {{ network.mac }}
            <CopyIcon :value="network.mac" class="opacity-80" size="xs" stroke-color="base-white" />
          </div>
        </div>

        <Button
          v-if="
            index == (props.fullHeight ? 3 : 1) &&
            networks.networks.length > (props.fullHeight ? 4 : 2)
          "
          variant="ghost"
          class="bg-white/20 backdrop-blur-sm rounded-md hover:bg-white/30 transition-colors h-6 text-xs font-semibold text-white/80"
          @click="emit('showNetworksModal')"
        >
          +{{ networks.networks.length - (props.fullHeight ? 4 : 2) }}
        </Button>
      </div>
    </div>
  </template>
</template>
