<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  abortStorageOperationsMutation,
  getStorageQueryKey,
  getStorageTaskQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { toast } from '@/components/ui/toast'

const { t } = useI18n()
const queryClient = useQueryClient()

interface Props {
  open?: boolean
  storageId: string
  desktopName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const {
  mutate: abortOperations,
  isPending,
  isError
} = useMutation({
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
    toast.success(t('components.desktops.desktop-storage-modal.cancel-modal.success'))
    // The mutation settles only after this callback, so `handleClose` would still
    // see it pending and swallow the close.
    emit('close')
  }
})

const handleClose = () => {
  if (isPending.value) return
  emit('close')
}
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    :size="isError ? 'lg' : 'md'"
    :title="t('components.desktops.desktop-storage-modal.cancel-modal.title')"
    :description="
      t('components.desktops.desktop-storage-modal.cancel-modal.description', {
        name: props.desktopName ?? ''
      })
    "
    @close="handleClose"
  >
    <template #description>
      <Alert v-if="isError" variant="destructive" class="mt-4">
        <AlertTitle>{{
          t('components.desktops.desktop-storage-modal.cancel-modal.error-title')
        }}</AlertTitle>
        <AlertDescription class="whitespace-pre-line">{{
          t('components.desktops.desktop-storage-modal.cancel-modal.error-description')
        }}</AlertDescription>
      </Alert>
    </template>

    <template #footer>
      <Button hierarchy="link-gray" :disabled="isPending" @click="handleClose">
        {{ t('components.desktops.desktop-storage-modal.cancel-modal.dismiss') }}
      </Button>
      <Button
        hierarchy="destructive"
        :disabled="isPending"
        @click="abortOperations({ path: { storage_id: props.storageId } })"
      >
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
