<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4'

import { AlertModal, Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'

import DesktopStorageItem from './DesktopStorageItem.vue'

interface Props {
  open: boolean
  desktop?: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {
  desktop: undefined
})

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()

const storageIds = computed<string[]>(() => {
  const ids = props.desktop?.storage ?? []
  return ids.filter((id): id is string => typeof id === 'string' && id.length > 0)
})

const errorModal = ref<{ description: string } | null>(null)

// Close any inline error modal whenever the parent closes the dialog so
// state doesn't leak between desktops.
watch(
  () => props.open,
  (open) => {
    if (!open) errorModal.value = null
  }
)
</script>

<template>
  <Modal
    :open="props.open"
    size="lg"
    :title="
      t('components.desktops.desktop-storage-modal.title', { name: props.desktop?.name ?? '' })
    "
    :description="t('components.desktops.desktop-storage-modal.description')"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-3 py-4">
      <p v-if="storageIds.length === 0" class="text-sm text-gray-warm-600">
        {{ t('components.desktops.desktop-storage-modal.no-storages') }}
      </p>
      <DesktopStorageItem
        v-for="id in storageIds"
        :key="id"
        :storage-id="id"
        :desktop="props.desktop!"
        @error="(msg) => (errorModal = { description: msg })"
      />
    </div>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.desktops.desktop-storage-modal.close') }}
      </Button>
    </template>
  </Modal>

  <AlertModal
    v-if="errorModal"
    :open="!!errorModal"
    level="danger"
    size="md"
    :title="t('components.desktops.desktop-storage-modal.error.title')"
    :description="errorModal.description"
    @close="errorModal = null"
  >
    <template #footer>
      <Button hierarchy="primary" @click="errorModal = null">
        {{ t('components.desktops.desktop-storage-modal.error.close') }}
      </Button>
    </template>
  </AlertModal>
</template>
