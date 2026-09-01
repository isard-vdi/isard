<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import DesktopStorageItem from '../desktop-storage-modal/DesktopStorageItem.vue'

interface Props {
  desktop?: UserDesktop
  showId?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  desktop: undefined,
  showId: false
})

const emit = defineEmits<{
  error: [message: string]
  success: []
}>()

const { t } = useI18n()

const storageIds = computed<string[]>(() => {
  const ids = props.desktop?.storage ?? []
  return ids.filter((id): id is string => typeof id === 'string' && id.length > 0)
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <p v-if="storageIds.length === 0" class="text-sm text-gray-warm-600">
      {{ t('components.desktops.desktop-storage-modal.no-storages') }}
    </p>
    <DesktopStorageItem
      v-for="id in storageIds"
      :key="id"
      :storage-id="id"
      :desktop="props.desktop!"
      :show-id="props.showId"
      @error="(msg) => emit('error', msg)"
      @success="emit('success')"
    />
  </div>
</template>
