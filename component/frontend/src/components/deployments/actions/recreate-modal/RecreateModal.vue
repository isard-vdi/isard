<script setup lang="ts">
import { useMutation } from '@tanstack/vue-query'
import { recreateDeploymentMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { useI18n } from 'vue-i18n'
import { cn } from '@/lib/utils'

const { t } = useI18n()

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

const handleClose = () => {
  emit('update:open', false)
  emit('close')
}

const { mutate: recreateDeploymentMutation, isPending: recreateDeploymentIsPending } = useMutation({
  ...recreateDeploymentMutation(),
  onSuccess: () => {
    handleClose()
    if (props.onSuccess) props.onSuccess()
  }
})

const handleRecreateDeployment = () => {
  if (!props.deploymentId) return
  recreateDeploymentMutation({
    path: { deployment_id: props.deploymentId }
  })
}
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    size="md"
    :title="t('views.deployment.recreate-modal.title', { name: deploymentName })"
    :description="t('views.deployment.recreate-modal.description')"
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="handleClose">
        {{ t('components.stop-all-desktops-confirmation-modal.cancel') }}
      </Button>

      <Button
        hierarchy="destructive"
        :icon="recreateDeploymentIsPending ? 'loading-02' : 'refresh-cw-04'"
        :icon-class="
          cn(recreateDeploymentIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
        "
        :disabled="recreateDeploymentIsPending"
        @click="handleRecreateDeployment()"
      >
        {{ t('views.deployment.recreate-modal.button') }}
      </Button>
    </template>
  </AlertModal>
</template>
