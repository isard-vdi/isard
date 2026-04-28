<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  deleteRecycleBinEntryMutation,
  getRecycleBinItemCountUserOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

interface Props {
  open?: boolean
  recycleBinId: string
  itemName?: string | null
  onSuccess?: () => void
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const { mutate: deleteEntry, isPending: deleteIsPending } = useMutation({
  ...deleteRecycleBinEntryMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({
      queryKey: getRecycleBinItemCountUserOptions()
    })
    handleClose()
    if (props.onSuccess) {
      props.onSuccess()
    }
  }
})

const entryNameLabel = computed(
  () => props.itemName || t('components.recycle-bin.permanent-delete-modal.unknown-item')
)

const confirmDelete = () => {
  if (!props.recycleBinId) return
  deleteEntry({ path: { recycle_bin_id: props.recycleBinId } })
}

const handleClose = () => {
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <AlertModal
    :open="props.open"
    level="danger"
    size="md"
    :loading="deleteIsPending"
    :title="t('components.recycle-bin.permanent-delete-modal.title', { name: entryNameLabel })"
    :description="t('components.recycle-bin.permanent-delete-modal.description')"
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" :disabled="deleteIsPending" @click="handleClose">
        {{ t('components.recycle-bin.permanent-delete-modal.cancel') }}
      </Button>
      <Button hierarchy="destructive" :disabled="deleteIsPending" @click="confirmDelete">
        <Icon
          v-if="deleteIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.recycle-bin.permanent-delete-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
