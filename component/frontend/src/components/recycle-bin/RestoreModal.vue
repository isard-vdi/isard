<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { restoreRecycleBinMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
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

const restoreError = ref('')

const { mutate: restoreEntry, isPending: restoreIsPending } = useMutation({
  ...restoreRecycleBinMutation(),
  onSuccess: () => {
    restoreError.value = ''
    handleClose()
    if (props.onSuccess) {
      props.onSuccess()
    }
  },
  onError: (error: any) => {
    const descriptionCode = error?.description_code
    if (descriptionCode) {
      const errorKey = `components.recycle-bin.restore-modal.errors.${descriptionCode}`
      restoreError.value = t(errorKey, t('components.recycle-bin.restore-modal.errors.generic'))
    } else {
      restoreError.value = t('components.recycle-bin.restore-modal.errors.generic')
    }
  }
})

const entryNameLabel = computed(
  () => props.itemName || t('components.recycle-bin.restore-modal.unknown-item')
)

const confirmRestore = () => {
  if (!props.recycleBinId) return
  restoreError.value = ''
  restoreEntry({ path: { recycle_bin_id: props.recycleBinId } })
}

const handleClose = () => {
  restoreError.value = ''
  emit('update:open', false)
  emit('close')
}

watch(
  () => props.open,
  (val) => {
    if (val) restoreError.value = ''
  }
)
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    size="md"
    :title="t('components.recycle-bin.restore-modal.title', { name: entryNameLabel })"
    :description="t('components.recycle-bin.restore-modal.description')"
    :loading="restoreIsPending"
    @close="handleClose"
  >
    <template #description>
      <div v-if="restoreError" class="mt-3 rounded-md border border-error-200 bg-error-50 p-3">
        <p class="text-sm font-medium text-error-700">{{ restoreError }}</p>
      </div>
    </template>
    <template #footer>
      <Button hierarchy="link-gray" :disabled="restoreIsPending" @click="handleClose">
        {{ t('components.recycle-bin.restore-modal.cancel') }}
      </Button>
      <Button hierarchy="primary" :disabled="restoreIsPending" @click="confirmRestore">
        <Icon
          v-if="restoreIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.recycle-bin.restore-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
