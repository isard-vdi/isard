<script setup lang="ts">
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  getDeploymentOptions,
  getUserConfigOptions,
  stopAllDesktopsInDeploymentMutation,
  deleteUserDeploymentDesktopsMutation,
  stopUserDesktopsInDeploymentMutation,
  toggleDeploymentVisibilityMutation,
  recreateDeploymentMutation,
  toggleDesktopDeploymentVisibilityMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { getDeploymentCsv, getDeploymentBastionCsv } from '@/gen/oas/apiv4/sdk.gen'

import Input from '@/components/ui/input/Input.vue'
import Button from '@/components/ui/button/Button.vue'
import DropdownButton from '@/components/dropdown-button/DropdownButton.vue'
import DataTable from '@/components/data-table/DataTable.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import Icon from '@/components/icon/Icon.vue'
import AlertModal from '@/components/modal/AlertModal.vue'
import DeploymentBastionModal from '@/components/deployments/DeploymentBastionModal.vue'
import DeploymentUserBastionModal from '@/components/deployments/DeploymentUserBastionModal.vue'
import { useDeleteDeployment } from '@/lib/deployments'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { useI18n } from 'vue-i18n'
import Switch from '@/components/ui/switch/Switch.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const { t } = useI18n()

const route = useRoute()
const labId = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id

const {
  isPending: deploymentIsPending,
  isError: deploymentIsError,
  error: deploymentError,
  data: deploymentData
} = useQuery(
  getDeploymentOptions({
    path: { deployment_id: labId }
  })
)

const isPending = computed(() => deploymentIsPending.value)
const isError = computed(() => deploymentIsError.value)
const error = computed(() => deploymentError.value)
const data = computed(() => deploymentData.value)

const { data: userConfig } = useQuery(getUserConfigOptions())
const canUseBastion = computed(() => userConfig.value?.can_use_bastion === true)

const showStopAllModal = ref(false)
const stopAllError = ref('')

const { mutate: stopAllDesktops, isPending: isStopping } = useMutation(
  stopAllDesktopsInDeploymentMutation()
)

const { mutate: toggleVisibilityMutation, isPending: isTogglingVisibility } = useMutation(
  toggleDeploymentVisibilityMutation()
)

const queryClient = useQueryClient()

function showStopAllConfirmation() {
  showStopAllModal.value = true
  stopAllError.value = ''
}

function confirmStopAll() {
  stopAllDesktops(
    { path: { deployment_id: labId } },
    {
      onSuccess: () => {
        showStopAllModal.value = false
        queryClient.invalidateQueries(['getDeployment'])
      },
      onError: () => {
        stopAllError.value = t('views.deployment.stop-all.error')
      }
    }
  )
}

function getStopAllModalDescription() {
  if (isStopping.value) {
    return t('views.deployment.stop-all.loading')
  }

  if (stopAllError.value) {
    return stopAllError.value
  }

  return t('views.deployment.stop-all.description')
}

const showToggleLabVisibilityModal = ref(false)
const isLabVisibilityGoingHidden = computed(() => {
  return !!data.value?.tag_visible
})

function toggleVisibility() {
  showToggleLabVisibilityModal.value = true
}

function confirmToggleLabVisibility({ stopAll = false } = {}) {
  toggleVisibilityMutation(
    { path: { deployment_id: labId } },
    {
      onSuccess: () => {
        if (stopAll) {
          stopAllDesktops(
            { path: { deployment_id: labId } },
            {
              onSuccess: () => {
                queryClient.invalidateQueries(['getDeployment'])
                showToggleLabVisibilityModal.value = false
              }
            }
          )
        } else {
          queryClient.invalidateQueries(['getDeployment'])
          showToggleLabVisibilityModal.value = false
        }
      }
    }
  )
}

const showStopUserModal = ref(false)
const stopUserError = ref('')
const currentUser = ref('')

const { mutate: stopUserDesktops, isPending: isStoppingUser } = useMutation(
  stopUserDesktopsInDeploymentMutation()
)

function showStopUserConfirmation(userId: string) {
  currentUser.value = userId
  showStopUserModal.value = true
  stopUserError.value = ''
}

function confirmStopUser() {
  stopUserDesktops(
    {
      path: {
        deployment_id: labId,
        user_id: currentUser.value
      }
    },
    {
      onSuccess: () => {
        showStopUserModal.value = false
        queryClient.invalidateQueries(['getDeployment'])
      },
      onError: () => {
        stopUserError.value = t('views.deployment.stop-user.error')
      }
    }
  )
}

function getStopUserModalDescription() {
  if (isStoppingUser.value) {
    return t('views.deployment.stop-user.loading')
  }

  if (stopUserError.value) {
    return stopUserError.value
  }

  return t('views.deployment.stop-user.description')
}

function enterVideowall({ path }: { path: { deployment_id: string } }) {
  window.location.href = '/deployment/' + path.deployment_id + '/videowall/'
}

function enterUserVideowall({ path }: { path: { deployment_id: string; user_id: string } }) {
  window.location.href = '/deployment/' + path.deployment_id + '/videowall/'
}

function downloadDirectViewer({ path }: { path: { deployment_id: string | number } }) {
  getDeploymentCsv({
    path: { deployment_id: path.deployment_id }
  }).then((response) => {
    if (!response.data) {
      throw new Error('No data received')
      // TODO: Should be an alert modal or similar to notify the user
    } else {
      let csvData = response.data as string
      if (csvData.startsWith('"') && csvData.endsWith('"')) {
        csvData = csvData
          .slice(1, -1)
          .replace(/""/g, '"')
          .replace(/\\r\\n|\\n/g, '\n')
      }
      const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const el = document.createElement('a')
      el.href = url
      el.download = `${path.deployment_id}_direct_viewer.csv`
      document.body.appendChild(el)
      el.click()
      setTimeout(() => {
        document.body.removeChild(el)
        window.URL.revokeObjectURL(url)
      }, 100)
    }
  })
}

function downloadBastionCsv({ path }: { path: { deployment_id: string | number } }) {
  getDeploymentBastionCsv({
    path: { deployment_id: path.deployment_id }
  }).then((response) => {
    if (!response.data) {
      throw new Error('No data received')
      // TODO: Should be an alert modal or similar to notify the user
    } else {
      let csvData = response.data as string
      if (csvData.startsWith('"') && csvData.endsWith('"')) {
        csvData = csvData
          .slice(1, -1)
          .replace(/""/g, '"')
          .replace(/\\r\\n|\\n/g, '\n')
      }
      const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const el = document.createElement('a')
      el.href = url
      el.download = `${path.deployment_id}_bastion.csv`
      document.body.appendChild(el)
      el.click()
      setTimeout(() => {
        document.body.removeChild(el)
        window.URL.revokeObjectURL(url)
      }, 100)
    }
  })
}

function goToEditLab(id: string): void {
  router.push(`/lab/edit/${id}`)
}

// function seeAttachments({ path }: { path: { deployment_id: string | number; user_id: string } }) {
//   // TODO: Add logic here to handle viewing attachments
// }

function formatTimestamp(timestamp: string | number | Date): string {
  let date: Date

  if (typeof timestamp === 'number' && timestamp < 1e12) {
    date = new Date(timestamp * 1000)
  } else {
    date = new Date(timestamp)
  }

  if (isNaN(date.getTime())) {
    return t('common.invalid-date')
  }

  const timeFormatter = new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit'
  })

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  })

  return `${timeFormatter.format(date)} - ${dateFormatter.format(date)}`
}

function goBack() {
  router.go(-1)
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

const headers = computed(() => [
  { name: t('views.deployment.headers.visible'), key: 'visible' },
  { name: t('views.deployment.headers.last-access'), key: 'accessed' },
  { name: t('views.deployment.headers.user'), key: 'user' },
  { name: t('views.deployment.headers.started-desktops'), key: 'started' },
  { name: t('views.deployment.headers.actions'), key: 'actions' },
  { name: '', key: 'menu' }
])
const rows = computed(() => {
  if (!deploymentData.value) return []

  const users = deploymentData.value.lab_users

  // Filter out users with 0 total desktops
  return users
    .filter((user) => user.total_desktops > 0)
    .map((user) => ({
      visible: Boolean(user.visible),
      accessed: formatTimestamp(user.accessed),
      user: user.username,
      user_id: user.id,
      started: user.started_desktops,
      total: user.total_desktops,
      actions: null,
      menu: []
    }))
})

const hasReservable = computed(() => {
  const createDict = data.value?.create_dict || []
  return createDict.some((item: Record<string, unknown>) => {
    if (!item.reservables) return false
    return Object.values(item.reservables).some((v) => (Array.isArray(v) ? v.length > 0 : !!v))
  })
})

const menuLab = computed(() => [
  {
    icon: 'edit-01',
    text: t('views.deployment.menu.edit'),
    onClick: () => goToEditLab(labId)
  },
  {
    icon: 'link-01',
    text: t('views.deployments.actions.direct-viewer'),
    onClick: () => downloadDirectViewer({ path: { deployment_id: labId } })
  },
  ...(canUseBastion.value
    ? [
        {
          icon: 'globe-04',
          text: t('views.deployment.menu.bastion'),
          onClick: () => (showBastionConfigModal.value = true)
        },
        {
          icon: 'download-01',
          text: t('views.deployment.menu.bastion-csv'),
          onClick: () => downloadBastionCsv({ path: { deployment_id: labId } })
        }
      ]
    : []),
  {
    icon: 'refresh-cw-04',
    text: t('views.deployment.menu.recreate'),
    onClick: () => showRecreateConfirmation()
  },
  {
    icon: 'eye',
    text: t('views.deployment.menu.toggle-visibility'),
    onClick: () => toggleVisibility()
  },
  // {
  //   icon: 'colors',
  //   text: t('views.deployment.menu.create-template'),
  //   disabled: true,
  //   title: t('common.to-be-implemented')
  // },
  // {
  //   icon: 'calendar',
  //   text: t('views.deployment.menu.book'),
  //   disabled: !hasReservable.value || true,
  //   title: t('common.to-be-implemented')
  //   // API implementation for labs needed
  // },
  {
    icon: 'trash-04',
    text: t('views.deployment.menu.delete'),
    disabled: false,
    onClick: () => handleDelete(labId, data.value?.name || '')
  }
])

const showBastionConfigModal = ref(false)
const bastionUserModalData = ref<{ userId: string; username: string } | null>(null)

const searchUser = t('components.input.placeholder.search')
const searchTerm = ref('')

const filteredRows = computed(() => {
  if (!searchTerm.value) return rows.value

  return rows.value.filter((row) => {
    return row.user.toLowerCase().includes(searchTerm.value.toLowerCase())
  })
})

const showDeleteUserModal = ref(false)
const userToDelete = ref('')
const deleteUserError = ref('')
const { mutate: deleteUserDesktops, isPending: isDeletingUser } = useMutation(
  deleteUserDeploymentDesktopsMutation()
)

function showDeleteUserConfirmation({
  path
}: {
  path: { deployment_id: string; user_id: string }
}) {
  userToDelete.value = path.user_id
  showDeleteUserModal.value = true
  deleteUserError.value = ''
}

function confirmDeleteUser() {
  deleteUserDesktops(
    {
      path: {
        deployment_id: labId,
        user_id: userToDelete.value
      }
    },
    {
      onSuccess: () => {
        showDeleteUserModal.value = false
        queryClient.invalidateQueries(['getDeployment'])
      },
      onError: () => {
        deleteUserError.value = t('views.deployment.delete-user.error')
      }
    }
  )
}

function getDeleteUserModalDescription() {
  if (isDeletingUser.value) {
    return t('views.deployment.delete-user.loading')
  }

  if (deleteUserError.value) {
    return deleteUserError.value
  }

  return t('views.deployment.delete-user.description')
}

const showRecreateModal = ref(false)
const recreateError = ref('')
const { mutate: recreateDeployment, isPending: isRecreating } = useMutation(
  recreateDeploymentMutation()
)

function showRecreateConfirmation() {
  showRecreateModal.value = true
  recreateError.value = ''
}

function confirmRecreate() {
  recreateDeployment(
    { path: { deployment_id: labId } },
    {
      onSuccess: () => {
        showRecreateModal.value = false
        queryClient.invalidateQueries(['getDeployment'])
      },
      onError: () => {
        recreateError.value = t('views.deployment.recreate.error')
      }
    }
  )
}

function getRecreateModalDescription() {
  if (isRecreating.value) {
    return t('views.deployment.recreate.loading')
  }

  if (recreateError.value) {
    return recreateError.value
  }

  return t('views.deployment.recreate.description')
}

const { mutate: toggleUserDesktopsVisibility, isPending: isTogglingUserVisibility } = useMutation(
  toggleDesktopDeploymentVisibilityMutation()
)

const showToggleVisibilityModal = ref(false)
const userToToggle = ref(null)
const rowToTogglegoingHidden = ref(false)

function toggleUserVisibility(userId) {
  userToToggle.value = userId
  const user = rows.value.find((row) => row.user_id === userId)
  rowToTogglegoingHidden.value = user.visible
  showToggleVisibilityModal.value = true
}

function confirmToggleUserVisibility() {
  toggleUserDesktopsVisibility(
    {
      path: {
        deployment_id: labId,
        user_id: userToToggle.value
      }
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries(['getDeployment'])
        showToggleVisibilityModal.value = false
        userToToggle.value = null
      }
    }
  )
}
</script>

<template>
  <div class="w-full max-w-(--breakpoint-2xl) mx-auto px-4 sm:px-6 lg:px-12">
    <Button icon="arrow-left" hierarchy="link-color" class="text-md w-min -mx-4" @click="goBack">
      {{ t('layouts.single-page.go-back') }}
    </Button>
    <div class="flex justify-between h-full absolute p-8"></div>
    <div
      class="mt-4 mb-0 flex items-center justify-between bg-base-banner rounded-lg gap-4 p-4 px-6 border border-base-border w-full"
    >
      <div class="flex items-start gap-8">
        <img src="../assets/img/bannerLabs.svg" alt="Banner image" class="-my-4" />

        <div class="flex flex-col gap-4">
          <Badge
            v-if="data?.tag_visible"
            hierarchy="Visible"
            icon="eye"
            size="sm"
            class="shadow-xs w-fit"
            >{{ t('views.deployments.visibility.visible') }}</Badge
          >
          <Badge v-else hierarchy="Hidden" icon="eye" size="sm" class="shadow-xs w-fit">{{
            t('views.deployments.visibility.hidden')
          }}</Badge>

          <div class="flex items-center gap-1">
            <Icon :name="data?.kind === 'desktops' ? 'tv-03' : 'beaker-02'" />
            <h2 class="font-bold text-lg text-gray-warm-800 truncate max-w-140">
              {{ data?.name }}
            </h2>
          </div>
        </div>
      </div>

      <div class="flex gap-4">
        <div class="flex items-start bg-white p-4 rounded-lg border border-base-border">
          <div class="flex items-center justify-center w-12 h-12 bg-gray-warm-200 rounded-full">
            <Icon name="user-03" stroke-color="gray-warm-600" />
          </div>

          <div class="flex flex-col ml-4 mr-6">
            <span class="text-sm text-gray-800">{{ t('views.deployment.detail.users') }}</span>
            <span class="text-lg font-bold">{{ data?.users?.length || 0 }}</span>
          </div>
        </div>

        <div class="flex items-start bg-white p-4 rounded-lg border border-base-border">
          <div class="flex items-center justify-center w-12 h-12 bg-gray-warm-200 rounded-full">
            <Icon name="power-01" stroke-color="gray-warm-600" />
          </div>

          <div class="flex flex-col ml-4 mr-6">
            <span class="text-sm text-gray-800">{{
              t('views.deployment.detail.started-desktops')
            }}</span>
            <span class="text-lg font-bold">{{ data?.started_desktops }}</span>
          </div>
        </div>

        <div class="flex items-start bg-white p-4 rounded-lg border border-base-border">
          <div class="flex items-center justify-center w-12 h-12 bg-gray-warm-200 rounded-full">
            <Icon name="eye" stroke-color="gray-warm-600" />
          </div>

          <div class="flex flex-col ml-4 mr-6">
            <span class="text-sm text-gray-800">{{ t('views.deployment.detail.visible') }}</span>
            <span class="text-lg font-bold">{{ data?.visible_desktops }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="flex flex-col gap-4 pt-4 w-full">
      <div class="flex gap-4 items-center justify-between">
        <Input
          id="input"
          v-model="searchTerm"
          icon="search-lg"
          :placeholder="searchUser"
          size="md"
          :destructive="false"
        />

        <div class="flex gap-4">
          <!-- <Button
            :title="t('common.to-be-implemented')"
            disabled
            hierarchy="secondary-gray"
            size="sm"
            icon="users-01"
            icon-size="md"
            icon-stroke-color="gray-warm-400"
            >{{ t('views.deployment.buttons.users-and-groups') }}</Button
          > -->
          <Button
            :title="t('common.to-be-implemented')"
            hierarchy="secondary-gray"
            size="sm"
            icon="tv-03"
            icon-size="md"
            @click="enterVideowall({ path: { deployment_id: labId } })"
            >{{ t('views.deployment.buttons.videowall') }}</Button
          >
          <Button
            hierarchy="destructive"
            size="sm"
            icon="stop"
            icon-size="md"
            icon-stroke-color="base-white"
            @click="showStopAllConfirmation"
            >{{ t('views.deployment.buttons.stop-all') }}</Button
          >
          <DropdownButton :menu-content="menuLab" />
        </div>
      </div>

      <div class="bg-white rounded-lg border border-base-border overflow-hidden p-3">
        <div
          v-if="isPending"
          class="text-center text-gray-warm-500 flex justify-center items-center"
        >
          <Icon name="loading-03" size="sm" class="animate-spin" />
          <p>{{ t('api.data.loading') }}</p>
        </div>
        <div v-else-if="isError" class="text-center text-error-500">
          <p>{{ t('api.data.error') }}</p>
        </div>
        <DataTable v-else :headers="headers" :rows="filteredRows">
          <template #cell-visible="{ row }">
            <Switch
              :checked="Boolean(row.visible)"
              :disabled="isStopping || isTogglingUserVisibility"
              :class="{ 'cursor-wait': isStopping || isTogglingUserVisibility }"
              @update:checked="toggleUserVisibility(row.user_id)"
            />
          </template>
          <template #cell-accessed="{ row }">
            <span>{{ row.accessed }}</span>
          </template>
          <template #cell-user="{ row }">
            <span class="text-sm text-gray-800">{{ row.user }}</span>
          </template>
          <template #cell-started="{ row }">
            <span class="text-sm text-gray-800">{{ row.started }} / {{ row.total }}</span>
          </template>
          <template #cell-actions="{ row }">
            <div>
              <Button
                hierarchy="secondary-color"
                icon="arrow-circle-broken-right"
                icon-size="md"
                @click="enterDesktop({ path: { deployment_id: labId, user_id: row.user } })"
              >
                {{ t('views.deployment.actions.access') }}
              </Button>
              <Button
                v-if="row.started > 0"
                class="ml-4"
                hierarchy="destructive"
                icon="stop"
                icon-size="md"
                :disabled="isStopping"
                @click="showStopUserConfirmation(row.user_id)"
              >
                {{ t('views.deployment.actions.stop') }}
              </Button>
            </div>
          </template>
          <template #cell-menu="{ row }">
            <div class="flex gap-2">
              <!-- <Button
                hierarchy="link-gray"
                size="md"
                icon="tv-03"
                icon-size="md"
                :title="t('common.to-be-implemented')"
                disabled
                icon-stroke-color="gray-warm-300"
                @click="enterUserVideowall({ path: { deployment_id: labId, user_id: row.user } })"
              /> -->
              <Button
                v-if="canUseBastion"
                hierarchy="link-gray"
                size="md"
                icon="globe-04"
                icon-size="md"
                :title="t('views.deployment.user-bastion.title')"
                @click="bastionUserModalData = { userId: row.user_id, username: row.user }"
              />
              <Button
                hierarchy="link-gray"
                size="md"
                icon="trash-04"
                icon-size="md"
                :title="t('views.deployment.delete-user.title')"
                @click="
                  showDeleteUserConfirmation({
                    path: { deployment_id: labId, user_id: row.user_id }
                  })
                "
              />
            </div>
          </template>
        </DataTable>
      </div>
    </div>
    <DeploymentBastionModal
      v-if="showBastionConfigModal"
      :open="showBastionConfigModal"
      :deployment-id="labId"
      :deployment-name="data?.name || ''"
      @close="showBastionConfigModal = false"
    />
    <DeploymentUserBastionModal
      v-if="bastionUserModalData !== null"
      :open="bastionUserModalData !== null"
      :deployment-id="labId"
      :user-id="bastionUserModalData.userId"
      :username="bastionUserModalData.username"
      @close="bastionUserModalData = null"
    />
    <AlertModal
      :open="showStopAllModal"
      level="warning"
      :title="t('views.deployment.stop-all.title')"
      :description="getStopAllModalDescription()"
      :loading="isStopping"
      @confirm="confirmStopAll"
      @cancel="showStopAllModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showStopAllModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button size="lg" hierarchy="destructive" :disabled="loading" @click="confirmStopAll">
            {{ loading ? t('common.loading') : t('views.deployment.buttons.stop-all') }}
          </Button>
        </div>
      </template>
    </AlertModal>
    <AlertModal
      :open="showStopUserModal"
      level="warning"
      :title="t('views.deployment.stop-user.title')"
      :description="getStopUserModalDescription()"
      :loading="isStoppingUser"
      @confirm="confirmStopUser"
      @cancel="showStopUserModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showStopUserModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button size="lg" hierarchy="destructive" :disabled="loading" @click="confirmStopUser">
            {{ loading ? t('common.loading') : t('views.deployment.actions.stop') }}
          </Button>
        </div>
      </template>
    </AlertModal>
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
    <AlertModal
      :open="showDeleteUserModal"
      level="danger"
      :title="t('views.deployment.delete-user.title')"
      :description="getDeleteUserModalDescription()"
      :loading="isDeletingUser"
      @confirm="confirmDeleteUser"
      @cancel="showDeleteUserModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showDeleteUserModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button size="lg" hierarchy="destructive" :disabled="loading" @click="confirmDeleteUser">
            {{ loading ? t('common.loading') : t('views.deployment.delete-user.confirm') }}
          </Button>
        </div>
      </template>
    </AlertModal>
    <AlertModal
      :open="showRecreateModal"
      level="warning"
      :title="t('views.deployment.recreate.title')"
      :description="getRecreateModalDescription()"
      :loading="isRecreating"
      @confirm="confirmRecreate"
      @cancel="showRecreateModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showRecreateModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button size="lg" hierarchy="destructive" :disabled="loading" @click="confirmRecreate">
            {{ loading ? t('common.loading') : t('modals.confirm') }}
          </Button>
        </div>
      </template>
    </AlertModal>
    <AlertModal
      :open="showToggleVisibilityModal"
      level="info"
      :title="
        rowToTogglegoingHidden
          ? t('views.deployment.toggle-user-visibility.title-invisible')
          : t('views.deployment.toggle-user-visibility.title-visible')
      "
      :description="
        rowToTogglegoingHidden
          ? t('views.deployment.toggle-user-visibility.description-invisible')
          : t('views.deployment.toggle-user-visibility.description-visible')
      "
      :loading="isTogglingUserVisibility"
      @confirm="confirmToggleUserVisibility"
      @cancel="showToggleVisibilityModal = false"
    >
      <template #default="{ loading }">
        <div class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showToggleVisibilityModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button
            size="lg"
            hierarchy="primary"
            :disabled="loading"
            @click="confirmToggleUserVisibility"
          >
            {{ loading ? t('common.loading') : t('modals.confirm') }}
          </Button>
        </div>
      </template>
    </AlertModal>
    <AlertModal
      :open="showToggleLabVisibilityModal"
      level="info"
      :size="isLabVisibilityGoingHidden ? 'lg' : 'md'"
      :title="
        isLabVisibilityGoingHidden
          ? t('views.deployment.toggle-lab-visibility.title-invisible')
          : t('views.deployment.toggle-lab-visibility.title-visible')
      "
      :description="
        isLabVisibilityGoingHidden
          ? t('views.deployment.toggle-lab-visibility.description-invisible')
          : t('views.deployment.toggle-lab-visibility.description-visible')
      "
      :loading="isTogglingVisibility"
      @cancel="showToggleLabVisibilityModal = false"
    >
      <template #default="{ loading }">
        <div v-if="isLabVisibilityGoingHidden" class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showToggleLabVisibilityModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button
            size="lg"
            hierarchy="primary"
            :disabled="loading"
            @click="confirmToggleLabVisibility({ stopAll: false })"
          >
            {{ t('views.deployment.toggle-lab-visibility.only-hide') }}
          </Button>
          <Button
            size="lg"
            hierarchy="destructive"
            :disabled="loading"
            @click="confirmToggleLabVisibility({ stopAll: true })"
          >
            {{ t('views.deployment.toggle-lab-visibility.hide-and-stop') }}
          </Button>
        </div>
        <div v-else class="flex justify-between w-full px-6">
          <Button
            size="lg"
            hierarchy="link-color"
            :disabled="loading"
            @click="showToggleLabVisibilityModal = false"
          >
            {{ t('modals.cancel') }}
          </Button>
          <Button
            size="lg"
            hierarchy="primary"
            :disabled="loading"
            @click="confirmToggleLabVisibility()"
          >
            {{ loading ? t('common.loading') : t('modals.confirm') }}
          </Button>
        </div>
      </template>
    </AlertModal>
  </div>
</template>
