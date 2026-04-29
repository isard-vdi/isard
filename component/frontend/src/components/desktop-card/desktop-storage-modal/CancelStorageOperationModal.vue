<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  abortStorageOperationsMutation,
  getStorageQueryKey,
  getStorageTaskQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ErrorResponse } from '@/gen/oas/apiv4'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

interface Props {
  open: boolean
  storageId: string
  desktopName?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
  error: [message: string]
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const formatErrorDetail = (error: unknown): string => {
  const err = error as ErrorResponse | undefined
  return (
    err?.description ||
    err?.description_code ||
    t('components.desktops.desktop-storage-modal.cancel-modal.fallback-error')
  )
}

const { mutate: abortOperations, isPending } = useMutation({
  ...abortStorageOperationsMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({
      queryKey: getStorageQueryKey({
        path: { storage_id: props.storageId }
      })
    })
    queryClient.invalidateQueries({
      queryKey: getStorageTaskQueryKey({
        path: { storage_id: props.storageId }
      })
    })
    handleClose()
  },
  onError: (error) => {
    emit('error', formatErrorDetail(error))
    handleClose()
  }
})

const confirm = () => {
  abortOperations({ path: { storage_id: props.storageId } })
}

const handleClose = () => {
  if (isPending.value) return
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    size="md"
    :loading="isPending"
    :title="t('components.desktops.desktop-storage-modal.cancel-modal.title')"
    :description="
      t('components.desktops.desktop-storage-modal.cancel-modal.description', {
        name: props.desktopName ?? ''
      })
    "
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" :disabled="isPending" @click="handleClose">
        {{ t('components.desktops.desktop-storage-modal.cancel-modal.dismiss') }}
      </Button>
      <Button hierarchy="destructive" :disabled="isPending" @click="confirm">
        <Icon
          v-if="isPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.desktops.desktop-storage-modal.cancel-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
