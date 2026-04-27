<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  increaseStorageSizeApiV4ItemStorageStorageIdPriorityPriorityIncreaseIncrementPutMutation,
  getStorageApiV4ItemStorageStorageIdGetQueryKey,
  getStorageTaskApiV4ItemStorageStorageIdTaskGetQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ErrorResponse } from '@/gen/oas/apiv4'

import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import InputField from '@/components/input-field/InputField.vue'

interface Props {
  open: boolean
  storageId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
  error: [message: string]
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const increment = ref<number>(10)

// Reset the field whenever the modal is reopened so a previous value
// doesn't leak between desktops or aborted attempts.
watch(
  () => props.open,
  (open) => {
    if (open) increment.value = 10
  }
)

const formatErrorDetail = (error: unknown): string => {
  const err = error as ErrorResponse | undefined
  return (
    err?.description ||
    err?.description_code ||
    t('components.desktops.desktop-storage-modal.increase-modal.fallback-error')
  )
}

const { mutate: increaseSize, isPending } = useMutation({
  ...increaseStorageSizeApiV4ItemStorageStorageIdPriorityPriorityIncreaseIncrementPutMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({
      queryKey: getStorageApiV4ItemStorageStorageIdGetQueryKey({
        path: { storage_id: props.storageId }
      })
    })
    queryClient.invalidateQueries({
      queryKey: getStorageTaskApiV4ItemStorageStorageIdTaskGetQueryKey({
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

const submit = () => {
  if (isInvalid()) return
  increaseSize({
    path: {
      storage_id: props.storageId,
      // The apiv4 endpoint forces priority="low" for non-admins and
      // accepts "low"/"default"/"high" for admins. v1 always submits
      // "low" to match v3's @is_not_user behaviour.
      priority: 'low',
      increment: increment.value
    }
  })
}

const handleClose = () => {
  if (isPending.value) return
  emit('update:open', false)
  emit('close')
}

const isInvalid = (): boolean =>
  !Number.isFinite(increment.value) || increment.value <= 0 || !Number.isInteger(increment.value)
</script>

<template>
  <Modal
    :open="props.open"
    size="md"
    :title="t('components.desktops.desktop-storage-modal.increase-modal.title')"
    :description="t('components.desktops.desktop-storage-modal.increase-modal.description')"
    :close-on-backdrop-click="!isPending"
    @close="handleClose"
  >
    <form class="flex flex-col gap-3 py-4" @submit.prevent="submit">
      <label class="text-sm font-semibold text-gray-warm-700" for="storage-increment">
        {{ t('components.desktops.desktop-storage-modal.increase-modal.field-label') }}
      </label>
      <InputField
        id="storage-increment"
        v-model="increment"
        type="number"
        :min="1"
        :step="1"
        :destructive="isInvalid()"
        :disabled="isPending"
        :placeholder="
          t('components.desktops.desktop-storage-modal.increase-modal.field-placeholder')
        "
      />
      <p class="text-xs text-gray-warm-500">
        {{ t('components.desktops.desktop-storage-modal.increase-modal.help') }}
      </p>
    </form>
    <template #footer>
      <Button hierarchy="link-gray" :disabled="isPending" @click="handleClose">
        {{ t('components.desktops.desktop-storage-modal.increase-modal.dismiss') }}
      </Button>
      <Button hierarchy="primary" :disabled="isPending || isInvalid()" @click="submit">
        <Icon
          v-if="isPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.desktops.desktop-storage-modal.increase-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
