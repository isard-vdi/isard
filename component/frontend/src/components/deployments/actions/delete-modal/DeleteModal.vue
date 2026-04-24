<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery } from '@tanstack/vue-query'
import {
  getRecycleBinDefaultDeleteConfigOptions,
  getRecycleBinCutoffTimeOptions,
  deleteDeploymentMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

interface Props {
  open?: boolean
  deploymentId: string
  deploymentName?: string | null
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

const { data: recycleBinDefaultDelete } = useQuery(
  getRecycleBinDefaultDeleteConfigOptions()
)

const { data: recycleBinCutoffTime } = useQuery(
  getRecycleBinCutoffTimeOptions()
)

const deleteModalRecycleBinChecked = ref(recycleBinDefaultDelete.value)

watch(recycleBinDefaultDelete, (val) => {
  deleteModalRecycleBinChecked.value = val
})

const { mutate: deleteDeploymentMutation, isPending: deleteDeploymentIsPending } = useMutation({
  ...deleteDeploymentMutation(),
  onSuccess: () => {
    handleClose()
    if (props.onSuccess) {
      props.onSuccess()
    }
  }
})

const deploymentNameLabel = computed(() => props.deploymentName || undefined)

const confirmDelete = () => {
  if (!props.deploymentId) return
  deleteDeploymentMutation({
    path: { deployment_id: props.deploymentId },
    query: {
      permanent:
        recycleBinCutoffTime.value?.recycle_bin_cutoff_time === 0 ||
        !deleteModalRecycleBinChecked.value
    }
  })
}

const handleClose = () => {
  deleteModalRecycleBinChecked.value = recycleBinDefaultDelete.value
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <AlertModal
    :open="props.open"
    level="danger"
    size="lg"
    :loading="deleteDeploymentIsPending"
    :title="
      t('components.delete-confirmation-modal.title', {
        kind: t('domains.with-article.deployments', 1),
        name: deploymentNameLabel
      })
    "
    @close="handleClose"
  >
    <template #description>
      <Label
        v-if="recycleBinCutoffTime?.recycle_bin_cutoff_time"
        class="w-fit flex flex-row items-start gap-2"
      >
        <Checkbox v-model="deleteModalRecycleBinChecked" class="m-0.5" />
        <div class="flex flex-col">
          <span>{{ t('components.delete-confirmation-modal.description.recycle-bin.title') }}</span>
          <span class="text-muted-foreground text-xs">{{
            t('components.delete-confirmation-modal.description.recycle-bin.subtitle', {
              hours: recycleBinCutoffTime?.recycle_bin_cutoff_time
            })
          }}</span>
        </div>
      </Label>
      <Label v-else class="w-fit flex flex-row items-start gap-0">{{
        t('components.delete-confirmation-modal.description.permanent.title')
      }}</Label>
    </template>
    <template #footer>
      <Button hierarchy="link-gray" :disabled="deleteDeploymentIsPending" @click="handleClose">
        {{ t('components.recycle-bin.permanent-delete-modal.cancel') }}
      </Button>
      <Button hierarchy="destructive" :disabled="deleteDeploymentIsPending" @click="confirmDelete">
        <Icon
          v-if="deleteDeploymentIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.recycle-bin.permanent-delete-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
