import { ref } from 'vue'
import type { Ref } from 'vue' // Change this line to use "type" import
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { deleteDeploymentMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useI18n } from 'vue-i18n'

export interface DeploymentToDelete {
  id: string
  name: string
}

export interface DeleteDeploymentState {
  showDeleteModal: Ref<boolean>
  deploymentToDelete: Ref<DeploymentToDelete | null>
  deleteLoading: Ref<boolean>
  deleteError: Ref<string>
  handleDelete: (deploymentId: string, deploymentName: string) => void
  confirmDelete: () => void
  getDeleteModalDescription: () => string
}

/**
 * Utility for managing deployment deletion across the application
 * @param onSuccessCallback Optional callback to execute after successful deletion
 * @returns Object with state and methods for delete functionality
 */
export function useDeleteDeployment(): DeleteDeploymentState {
  const { t } = useI18n()

  const showDeleteModal = ref(false)
  const deploymentToDelete = ref<DeploymentToDelete | null>(null)
  const deleteLoading = ref(false)
  const deleteError = ref('')

  const deleteMutation = useMutation(deleteDeploymentMutation())

  function handleDelete(deploymentId: string, deploymentName: string) {
    deploymentToDelete.value = { id: deploymentId, name: deploymentName }
    showDeleteModal.value = true
    deleteError.value = ''
  }

  function confirmDelete() {
    if (!deploymentToDelete.value) return

    deleteLoading.value = true
    deleteError.value = ''

    deleteMutation.mutate(
      {
        path: {
          deployment_id: deploymentToDelete.value.id
        }
      },
      {
        onSuccess: () => {
          deleteLoading.value = false
          showDeleteModal.value = false
        },
        onError: () => {
          deleteLoading.value = false
          deleteError.value = t('views.deployments.delete.error')
        }
      }
    )
  }

  function getDeleteModalDescription() {
    if (deleteLoading.value) {
      return t('views.deployments.delete.loading')
    }

    if (deleteError.value) {
      return deleteError.value
    }

    return deploymentToDelete.value
      ? t('views.deployments.delete.description', { name: deploymentToDelete.value.name })
      : ''
  }

  return {
    showDeleteModal,
    deploymentToDelete,
    deleteLoading,
    deleteError,
    handleDelete,
    confirmDelete,
    getDeleteModalDescription
  }
}
