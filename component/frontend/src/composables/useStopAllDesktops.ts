import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  getDeploymentQueryKey,
  getDeploymentVideowallQueryKey,
  stopAllDesktopsInDeploymentMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { toast } from '@/components/ui/toast'

export interface StopAllCounts {
  started: number
  shuttingDown: number
  stopping: number
}

/** "Stop all" of a deployment: the button state, its confirmation modal and the request. */
export function useStopAllDesktops(
  deploymentId: MaybeRefOrGetter<string>,
  counts: MaybeRefOrGetter<StopAllCounts>
) {
  const { t } = useI18n()
  const queryClient = useQueryClient()

  const showStopAllModal = ref(false)
  const stopAllError = ref('')

  const { mutate: stopAllDesktops, isPending: stopAllIsPending } = useMutation({
    ...stopAllDesktopsInDeploymentMutation(),
    onSuccess: () => {
      showStopAllModal.value = false
      const options = { path: { deployment_id: toValue(deploymentId) } }
      queryClient.invalidateQueries({ queryKey: getDeploymentQueryKey(options) })
      queryClient.invalidateQueries({ queryKey: getDeploymentVideowallQueryKey(options) })
    },
    onError: () => {
      if (showStopAllModal.value) {
        stopAllError.value = t('views.deployment.stop-all.error')
      } else {
        toast.error(t('views.deployment.stop-all.error'))
      }
    }
  })

  // Desktops already shutting down still count as stoppable: a graceful stop
  // skips them, but a forced one kills them, and that is the only way out of a
  // guest that ignored the shutdown request.
  const anyDesktopStoppable = computed(() => {
    const { started, shuttingDown } = toValue(counts)
    return started > 0 || shuttingDown > 0
  })

  // Stopping is the only stop state the button cannot act on, so it is the one
  // that reads as work in progress rather than as something to click.
  const isStoppingAll = computed(() => stopAllIsPending.value || toValue(counts).stopping > 0)

  const openStopAllModal = () => {
    stopAllError.value = ''
    showStopAllModal.value = true
  }

  const closeStopAllModal = () => {
    showStopAllModal.value = false
    stopAllError.value = ''
  }

  const confirmStopAll = (force: boolean) => {
    stopAllError.value = ''
    stopAllDesktops({
      path: { deployment_id: toValue(deploymentId) },
      body: { force }
    })
  }

  return {
    showStopAllModal,
    stopAllError,
    stopAllIsPending,
    anyDesktopStoppable,
    isStoppingAll,
    openStopAllModal,
    closeStopAllModal,
    confirmStopAll
  }
}
