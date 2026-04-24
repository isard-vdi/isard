<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import DataTable from '@/components/data-table/DataTable.vue'
import ToggleText from '@/components/toggle-text/ToggleText.vue'
import Icon from '@/components/icon/Icon.vue'
import DropdownButton from '@/components/dropdown-button/DropdownButton.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import Input from '@/components/ui/input/Input.vue'
import ModalCard from '@/components/modal-card/ModalCard.vue'
import Button from '@/components/ui/button/Button.vue'
import AlertModal from '@/components/modal/AlertModal.vue'
import {
  getAllDeploymentsOptions,
  deleteDeploymentMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useDeleteDeployment } from '@/lib/deployments'

import modalDeployment from '@/assets/img/modalcard-1.svg'
import modalLabs from '@/assets/img/modalcard-2.svg'

const { t } = useI18n()
const queryClient = useQueryClient()
const router = useRouter()
const { isPending, isError, data: deploymentsData } = useQuery(getAllDeploymentsOptions())

const deleteMutation = useMutation({
  ...deleteDeploymentMutation()
})
function goToDeploymentDetail(deploymentId: string) {
  router.push(`/lab/${deploymentId}`)
}

const {
  showDeleteModal,
  deploymentToDelete,
  deleteLoading,
  deleteError,
  handleDelete,
  confirmDelete,
  getDeleteModalDescription
} = useDeleteDeployment()

function goToEditLab(id: string): void {
  router.push(`/lab/edit/${id}`)
}

function goToForm(deploymentKind: string) {
  if (deploymentKind === 'lab') {
    router.push(`/${deploymentKind}/new`)
  } else if (deploymentKind === 'desktops') {
    window.location.href = 'deployments/new' // temporary solution. It should
  }
}
const headers = [
  { name: t('views.deployments.headers.kind'), key: 'kind' },
  { name: t('views.deployments.headers.visibility'), key: 'visibility' },
  { name: t('views.deployments.headers.name'), key: 'name' },
  { name: t('views.deployments.headers.description'), key: 'description' },
  { name: t('views.deployments.headers.desktop-names'), key: 'desktop_names' },
  { name: t('views.deployments.headers.started'), key: 'started' },
  { name: t('views.deployments.headers.visible'), key: 'visible' },
  { name: t('views.deployments.headers.total'), key: 'total' },
  { name: '', key: 'action' }
]

const toggleValue = ref('all')
const searchTerm = ref('')

const rows = computed(() => {
  if (!deploymentsData.value || !deploymentsData.value.deployments) return []

  return deploymentsData.value.deployments.map((deployment) => ({
    id: deployment.id,
    kind: deployment.kind,
    visibility: deployment.tag_visible,
    name: deployment.name,
    description: deployment.description || '',
    desktop_names: deployment.desktop_names.join(', '),
    started: deployment.started_desktops?.toString() || '0',
    visible: deployment.visible_desktops?.toString() || '0',
    total: deployment.total_desktops?.toString() || '0',
    action: [
      {
        icon: 'edit-01',
        text: t('views.deployments.actions.edit'),
        onClick: () => goToEditLab(deployment.id)
      },
      {
        icon: 'trash-04',
        text: t('views.deployments.actions.delete'),
        onClick: () => handleDelete(deployment.id, deployment.name)
      }
    ] as { icon: string; text: string; onClick: () => void }[]
  }))
})

const filteredRows = computed(() => {
  return rows.value.filter((row) => {
    const matchesSearch = row.name.toLowerCase().includes(searchTerm.value.toLowerCase())
    const isVisible = row.visibility === true
    const toggleFilter = toggleValue.value === 'all' || isVisible
    return matchesSearch && toggleFilter
  })
})

const inputProps = {
  defaultValue: '',
  placeholder: t('views.deployments.search'),
  size: 'sm',
  destructive: false,
  icon: 'search-lg'
}

const toggleTextProps = {
  left: { value: 'all', label: t('views.deployments.toggle.all') },
  right: { value: 'visible', label: t('views.deployments.toggle.visible') }
}

const options = [
  {
    kind: 'desktops',
    image: modalDeployment,
    title: t('modals.new-deployment.deployment.title'),
    description: t('modals.new-deployment.deployment.description')
    // TODO: implement handlers for modal options that goes to the deployment creation page
  },
  {
    kind: 'lab',
    image: modalLabs,
    title: t('modals.new-deployment.lab.title'),
    description: t('modals.new-deployment.lab.description')
    // TODO: implement handlers for modal options that goes to the lab creation page
  }
]
</script>

<template>
  <div class="w-full max-w-(--breakpoint-2xl) mx-auto px-4 sm:px-6 lg:px-12">
    <div class="mt-10 w-full">
      <div class="flex justify-between items-center mb-8">
        <Input v-bind="inputProps" v-model="searchTerm" />
        <div class="flex items-center gap-6">
          <ToggleText v-bind="toggleTextProps" v-model="toggleValue" />
          <ModalCard
            :title="t('modals.new-deployment.title')"
            :subtitle="t('modals.new-deployment.subtitle')"
            :options="options"
            @confirm="(kind) => goToForm(kind)"
          />
        </div>
      </div>

      <div class="overflow-x-auto bg-white rounded-lg border border-[#D7D3D0] p-6 w-full">
        <div
          v-if="isPending"
          class="text-center text-gray-warm-500 flex justify-center items-center"
        >
          <Icon name="loading-03" size="sm" class="animate-spin mr-2" />
          {{ t('views.deployments.loading') }}
        </div>
        <div v-else-if="isError" class="text-center text-error-500">
          {{ t('views.deployments.error') }}
        </div>
        <DataTable
          v-else
          :headers="headers"
          :rows="filteredRows"
          :is-clickable="true"
          @row-click="(row) => goToDeploymentDetail(row.id)"
        >
          <template #cell-kind="{ value }">
            <Icon
              :name="value === 'lab' ? 'beaker-02' : 'layout-alt-04'"
              :featured="value"
              size="xxl"
            />
          </template>
          <template #cell-visibility="{ value }">
            <Badge
              :hierarchy="value ? 'Visible' : 'Hidden'"
              size="sm"
              type="rounded"
              :icon="value ? 'eye' : 'eye-off'"
              style="cursor: default"
            >
              {{
                value
                  ? t('views.deployments.visibility.visible')
                  : t('views.deployments.visibility.hidden')
              }}
            </Badge>
          </template>
          <template #cell-started="{ value }">
            <Badge
              hierarchy="Info"
              size="sm"
              type="rounded"
              icon="power-01"
              style="cursor: default"
              :text="value"
              @click.stop
            >
              {{ value }}
            </Badge>
          </template>
          <template #cell-visible="{ value }">
            <Badge
              hierarchy="Info"
              size="sm"
              type="rounded"
              icon="eye"
              style="cursor: default"
              :text="value"
              @click.stop
            >
              {{ value }}
            </Badge>
          </template>
          <template #cell-total="{ value }">
            <Badge
              hierarchy="Info"
              size="sm"
              type="rounded"
              icon="monitor-02"
              style="cursor: default"
              :text="value"
              @click.stop
            >
              {{ value }}
            </Badge>
          </template>
          <template #cell-action="{ value }">
            <DropdownButton :menu-content="value" @click.stop />
          </template>
        </DataTable>
      </div>
    </div>

    <AlertModal
      :open="showDeleteModal"
      level="danger"
      :title="deploymentToDelete ? t('views.deployments.delete.title') : ''"
      :description="getDeleteModalDescription()"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @cancel="showDeleteModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showDeleteModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button size="lg" hierarchy="destructive" :disabled="loading" @click="confirmDelete">
            {{ loading ? t('common.loading') : t('views.deployments.actions.delete') }}
          </Button>
        </div>
      </template>
    </AlertModal>
  </div>
</template>
