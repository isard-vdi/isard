<script setup lang="ts">
import { computed } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import {
  countRecreateDeploymentDesktopsOptions,
  countRecreateDeploymentDesktopsQueryKey,
  recreateDeploymentMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { useI18n } from 'vue-i18n'
import { cn } from '@/lib/utils'
import { describeApiError } from '@/lib/api-errors'

const { t, te } = useI18n()

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

// Allowed users that are disabled, or that already have their desktop, are
// skipped by the recreate: only the API can say how many it will really create.
const {
  data: recreateCount,
  isPending: countIsPending,
  isFetching: countIsFetching,
  error: countError
} = useQuery({
  ...countRecreateDeploymentDesktopsOptions({ path: { deployment_id: props.deploymentId } }),
  queryKey: computed(() =>
    countRecreateDeploymentDesktopsQueryKey({ path: { deployment_id: props.deploymentId } })
  ),
  enabled: computed(() => props.open && !!props.deploymentId)
})

// isFetching too, so a refetch never leaves the previous deployment's count on screen.
const isCounting = computed(() => countIsPending.value || countIsFetching.value)
const desktopsToCreate = computed(() => recreateCount.value?.desktops_to_create ?? 0)
const canRecreate = computed(
  () => !isCounting.value && !countError.value && desktopsToCreate.value > 0
)

const level = computed(() => {
  if (countError.value) return 'danger' as const
  if (!isCounting.value && desktopsToCreate.value === 0) return 'info' as const
  return 'warning' as const
})

const description = computed(() => {
  if (isCounting.value) return t('views.deployment.recreate-modal.counting')
  if (countError.value) return describeApiError(countError.value, { t, te }, 'recreate-deployment')
  if (desktopsToCreate.value === 0) return t('views.deployment.recreate-modal.empty')
  return [
    t('views.deployment.recreate-modal.description'),
    t('views.deployment.recreate-modal.count', desktopsToCreate.value)
  ].join('\n')
})

const { mutate: recreateDeployment, isPending: recreateDeploymentIsPending } = useMutation({
  ...recreateDeploymentMutation(),
  onSuccess: () => {
    handleClose()
    if (props.onSuccess) props.onSuccess()
  }
})

const handleRecreateDeployment = () => {
  if (!props.deploymentId) return
  recreateDeployment({
    path: { deployment_id: props.deploymentId }
  })
}
</script>

<template>
  <AlertModal
    :open="props.open"
    :level="level"
    size="md"
    :title="t('views.deployment.recreate-modal.title', { name: deploymentName })"
    :description="description"
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="handleClose">
        {{
          canRecreate
            ? t('components.stop-all-desktops-confirmation-modal.cancel')
            : t('views.deployment.recreate-modal.close')
        }}
      </Button>

      <Button
        v-if="canRecreate"
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
