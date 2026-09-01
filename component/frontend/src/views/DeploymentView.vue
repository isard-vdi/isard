<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { Icon } from '@/components/icon'
import { AvatarLabel } from '@/components/avatar-label'
import { DataTable } from '@/components/data-table'
import bannerDeployments from '@/assets/img/banner-deployments.svg'
import {
  getDeploymentOptions,
  getUserConfigOptions,
  editDeploymentUsersMutation,
  getDeploymentAllowedQueryKey,
  getDeploymentCoOwnersOptions,
  getDeploymentCoOwnersQueryKey,
  updateDeploymentCoOwnersMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getDeploymentBastionCsv } from '@/gen/oas/apiv4/sdk.gen'
import { type DeploymentUserDetail, type ErrorResponse } from '@/gen/oas/apiv4'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/badge'
import { Switch } from '@/components/ui/switch'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import { useMediaQuery } from '@vueuse/core'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import { formatRelativeTime } from '@/lib/utils'
import { RecreateModal } from '@/components/deployments/actions/recreate-modal'
import { DeleteModal } from '@/components/deployments/actions/delete-modal'
import { DownloadCsvModal } from '@/components/deployments/actions/download-csv-modal'
import DeploymentBastionModal from '@/components/deployments/DeploymentBastionModal.vue'
import DeploymentUserBastionModal from '@/components/deployments/DeploymentUserBastionModal.vue'
import DeploymentProvisioningModal from '@/components/deployments/DeploymentProvisioningModal.vue'
import { useBulkSpawnStore } from '@/stores/bulk-spawn'
import { EmptyState, PageContainer, PageToolbar, SearchInput } from '@/components/page'
import { AllowedModal, type AllowedOption, type AllowedSelection } from '@/components/modal/allowed'
import { toast } from '@/components/ui/toast'

const { t, d, locale } = useI18n()

const router = useRouter()
const route = useRoute()
const deploymentId = computed(() => {
  const param = route.params.deploymentId || route.params.id
  if (Array.isArray(param)) return param[0] || ''
  return param || ''
})

const {
  isPending: deploymentEntryIsPending,
  data: deploymentEntry,
  isError: deploymentEntryIsError
} = useQuery({
  ...getDeploymentOptions({
    path: { deployment_id: deploymentId.value }
  })
})

watch(deploymentEntryIsError, (isError) => {
  if (isError) {
    router.replace({ name: 'deployments' })
  }
})

const visibilityBadgeClass = computed(() => {
  const isVisible = deploymentEntry.value?.info.tag_visible
  return {
    color: isVisible ? 'blue' : 'gray',
    content: isVisible
      ? t('views.deployments.visibility.visible')
      : t('views.deployments.visibility.hidden'),
    icon: isVisible ? 'eye' : 'eye-off',
    shape: 'square',
    class: 'gap-2'
  } as const
})

const filteredDeploymentUsers = computed(() => {
  const allDeploymentUsers = deploymentEntry.value?.users ?? []
  return allDeploymentUsers.filter(areUsersVisible)
})

const inputSearch = ref<string>('')

const hasDeploymentUsers = computed(() => (deploymentEntry.value?.users?.length ?? 0) > 0)

// Visibility
const areUsersVisible = (users: DeploymentUserDetail) => {
  const matchesSearch =
    inputSearch.value.toLowerCase() === '' ||
    users.name.toLowerCase().includes(inputSearch.value.toLowerCase())
  return matchesSearch
}

const header = computed(() => [
  {
    name: t('views.deployment.data-table.headers.visible'),
    key: 'visible',
    sortable: false,
    width: 'minmax(80px, max-content)'
  },
  {
    name: t('views.deployment.data-table.headers.last-access'),
    key: 'last_access',
    sortable: false,
    width: 'minmax(130px, auto)'
  },
  {
    name: t('views.deployment.data-table.headers.user'),
    key: 'name',
    sortable: true
  },
  {
    name: t('views.deployment.data-table.headers.started-desktops'),
    key: 'started_desktops',
    sortable: false,
    width: 'minmax(170px, auto)'
  },
  {
    name: t('views.deployment.data-table.headers.actions'),
    key: 'actions',
    sortable: false,
    width: 'minmax(min-content, var(--spacing-140))'
  }
])

const totalDesktops = computed(() => deploymentEntry.value?.info.desktops_each_user)

const isXL = useMediaQuery('(min-width: 1280px)')

const bulkSpawnStore = useBulkSpawnStore()
const isRecreatingDesktops = computed(() =>
  deploymentId.value ? bulkSpawnStore.deploymentsInProgress.has(deploymentId.value) : false
)

// Rows the engine has inserted but storage has not finished with yet: the
// bulk-spawn envelope alone misses a recreate whose fan-out already ended.
const CREATING_STATUSES: string[] = [
  DesktopStatusEnum.CREATING,
  DesktopStatusEnum.CREATING_DISK,
  DesktopStatusEnum.CREATING_AND_STARTING
]
const hasDesktopsBeingCreated = computed(() =>
  (deploymentEntry.value?.users ?? [])
    .flatMap((user) => user.desktops_statuses ?? [])
    .some((status) => CREATING_STATUSES.includes(status.status) && status.amount > 0)
)
const isProvisioning = computed(() => isRecreatingDesktops.value || hasDesktopsBeingCreated.value)

const showProvisioningModal = ref(false)
let provisioningCloseTimer: ReturnType<typeof setTimeout> | null = null

const clearProvisioningCloseTimer = () => {
  if (provisioningCloseTimer === null) return
  clearTimeout(provisioningCloseTimer)
  provisioningCloseTimer = null
}

// Held open for a moment after the last desktop lands, so both bars are seen
// full instead of the modal vanishing mid-progress.
watch(
  isProvisioning,
  (provisioning) => {
    clearProvisioningCloseTimer()
    if (provisioning) {
      showProvisioningModal.value = true
      return
    }
    if (!showProvisioningModal.value) return
    provisioningCloseTimer = setTimeout(() => {
      provisioningCloseTimer = null
      showProvisioningModal.value = false
    }, 2000)
  },
  { immediate: true }
)

onBeforeUnmount(clearProvisioningCloseTimer)

const { data: userConfig } = useQuery(getUserConfigOptions())
const canUseBastion = computed(() => userConfig.value?.can_use_bastion === true)

const showBastionConfigModal = ref(false)
const bastionUserModalData = ref<{ userId: string; username: string } | null>(null)

function downloadBastionCsv() {
  getDeploymentBastionCsv({
    path: { deployment_id: deploymentId.value }
  }).then((response) => {
    if (!response.data) return
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
    el.download = `${deploymentId.value}_bastion.csv`
    document.body.appendChild(el)
    el.click()
    setTimeout(() => {
      document.body.removeChild(el)
      window.URL.revokeObjectURL(url)
    }, 100)
  })
}

const dropdownActions = computed(() => [
  {
    key: 'edit',
    icon: 'edit-01',
    label: t('views.deployments.dropdown.buttons.edit'),
    fn: handleNotImplemented
  },
  {
    key: 'download',
    icon: 'download-02',
    label: t('views.deployments.dropdown.buttons.download-viewer'),
    fn: () => (showDownloadCsvModal.value = true)
  },
  ...(canUseBastion.value
    ? [
        {
          key: 'bastion',
          icon: 'globe-04',
          label: t('views.deployments.dropdown.buttons.bastion'),
          fn: () => (showBastionConfigModal.value = true)
        },
        {
          key: 'bastion-csv',
          icon: 'download-01',
          label: t('views.deployments.dropdown.buttons.bastion-csv'),
          fn: () => downloadBastionCsv()
        }
      ]
    : []),
  ...(deploymentEntry.value?.info.co_owner
    ? []
    : [
        {
          key: 'co-owners',
          icon: 'users-plus',
          label: t('views.deployments.dropdown.buttons.co-owners'),
          fn: () => openCoOwnersModal()
        }
      ]),
  {
    key: 'recreate',
    icon: 'refresh-cw-04',
    label: t('views.deployments.dropdown.buttons.recreate'),
    disabled: isRecreatingDesktops.value,
    fn: () => (showRecreateModal.value = true)
  },
  {
    key: 'reserve',
    icon: 'calendar',
    label: t('views.deployments.dropdown.buttons.reserve'),
    fn: handleNotImplemented
  },
  {
    key: 'delete',
    icon: 'trash-04',
    label: t('views.deployments.dropdown.buttons.delete'),
    destructive: true,
    fn: () => (showDeleteModal.value = true)
  }
])

const showRecreateModal = ref(false)

const closeRecreateModal = () => (showRecreateModal.value = false)

const showDeleteModal = ref(false)

const handleDeleteSuccess = () => {
  showDeleteModal.value = false
  router.push({ name: 'deployments' })
}
const showDownloadCsvModal = ref(false)

const handleNotImplemented = () => alert('not implemented yet')

const queryClient = useQueryClient()

const showCoOwnersModal = ref(false)
const coOwnersError = ref('')

const { data: coOwners } = useQuery({
  ...getDeploymentCoOwnersOptions({ path: { deployment_id: deploymentId.value } }),
  queryKey: computed(() =>
    getDeploymentCoOwnersQueryKey({ path: { deployment_id: deploymentId.value } })
  ),
  enabled: computed(() => showCoOwnersModal.value && !!deploymentId.value)
})

const coOwnersSelection = computed<AllowedSelection | undefined>(() =>
  coOwners.value
    ? { groups: false, users: coOwners.value.co_owners.map((user) => user.id) }
    : undefined
)

const coOwnersOwnerName = computed(() => coOwners.value?.owner.name ?? '')

const preselectedCoOwners = computed<AllowedOption[] | undefined>(() =>
  coOwners.value?.co_owners.map((user) => ({
    value: user.id,
    label: user.name,
    subLabel: user.uid ?? undefined,
    avatar: user.photo ?? ''
  }))
)

const { mutate: updateCoOwners, isPending: updateCoOwnersIsPending } = useMutation({
  ...updateDeploymentCoOwnersMutation(),
  onSuccess: (_data, variables) => {
    queryClient.removeQueries({
      queryKey: getDeploymentCoOwnersQueryKey({
        path: { deployment_id: variables.path.deployment_id }
      })
    })
    closeCoOwnersModal()
    toast.success(t('components.deployments.co-owners-modal.success'))
  },
  onError: () => {
    coOwnersError.value = t('components.deployments.co-owners-modal.error')
  }
})

const openCoOwnersModal = () => {
  coOwnersError.value = ''
  showCoOwnersModal.value = true
}

const closeCoOwnersModal = () => {
  showCoOwnersModal.value = false
  coOwnersError.value = ''
}

const handleSaveCoOwners = (selection: AllowedSelection) => {
  coOwnersError.value = ''
  updateCoOwners({
    path: { deployment_id: deploymentId.value },
    body: { co_owners: Array.isArray(selection.users) ? selection.users : [] }
  })
}

const showAllowedModal = ref(false)
const allowedError = ref('')

const { mutate: editDeploymentUsers, isPending: updateAllowedIsPending } = useMutation({
  ...editDeploymentUsersMutation(),
  onSuccess: (_data, variables) => {
    queryClient.removeQueries({
      queryKey: getDeploymentAllowedQueryKey({
        path: { deployment_id: variables.path.deployment_id }
      })
    })
    closeAllowedModal()
    toast.success(t('views.deployments.alloweds.success'))
  },
  onError: (error) => {
    allowedError.value =
      (error as ErrorResponse)?.description_code === 'cant_edit_booked_deployment'
        ? t('views.deployments.alloweds.blocked')
        : t('views.deployments.alloweds.error')
  }
})

const openAllowedModal = () => {
  allowedError.value = ''
  showAllowedModal.value = true
}

const closeAllowedModal = () => {
  showAllowedModal.value = false
  allowedError.value = ''
}

const handleSaveAllowed = (selection: AllowedSelection) => {
  allowedError.value = ''
  editDeploymentUsers({
    path: { deployment_id: deploymentId.value },
    body: { allowed: selection }
  })
}

const enterVideowall = () => {
  router.push({ name: 'deployment-videowall', params: { deploymentId: deploymentId.value } })
}

const DEPLOYMENT_SEARCH_INPUT_ID = 'deployment-search'
</script>

<template>
  <AllowedModal
    v-if="showCoOwnersModal"
    open
    users-only
    :roles="['advanced', 'manager', 'admin']"
    :supports-everyone="false"
    :selection="coOwnersSelection"
    :preselected-users="preselectedCoOwners"
    :title="t('components.deployments.co-owners-modal.title', { name: deploymentEntry?.info.name })"
    :description="
      t('components.deployments.co-owners-modal.description', { owner: coOwnersOwnerName })
    "
    :warning="t('components.deployments.co-owners-modal.warning')"
    :loading="updateCoOwnersIsPending"
    :error="coOwnersError"
    @save="handleSaveCoOwners"
    @close="closeCoOwnersModal"
  />
  <RecreateModal
    :open="showRecreateModal"
    :deployment-id="deploymentEntry?.info.id || ''"
    :deployment-name="deploymentEntry?.info.name"
    :onSuccess="closeRecreateModal"
    @close="closeRecreateModal"
  />
  <AllowedModal
    v-if="showAllowedModal"
    open
    item-type="deployment"
    :item-id="deploymentId"
    :warning="t('views.deployments.alloweds.warning')"
    require-selection
    :supports-everyone="false"
    :loading="updateAllowedIsPending"
    :error="allowedError"
    @save="handleSaveAllowed"
    @close="closeAllowedModal"
  />
  <DeleteModal
    v-model:open="showDeleteModal"
    :deployment-id="deploymentEntry?.info.id || ''"
    :deployment-name="deploymentEntry?.info.name"
    :on-success="handleDeleteSuccess"
  />
  <DownloadCsvModal
    v-model:open="showDownloadCsvModal"
    :deployment-id="deploymentEntry?.info.id || ''"
    :deployment-name="deploymentEntry?.info.name || ''"
  />
  <DeploymentBastionModal
    v-if="showBastionConfigModal"
    :open="showBastionConfigModal"
    :deployment-id="deploymentId"
    :deployment-name="deploymentEntry?.info.name || ''"
    @close="showBastionConfigModal = false"
  />
  <DeploymentUserBastionModal
    v-if="bastionUserModalData !== null"
    :open="bastionUserModalData !== null"
    :deployment-id="deploymentId"
    :user-id="bastionUserModalData.userId"
    :username="bastionUserModalData.username"
    @close="bastionUserModalData = null"
  />
  <DeploymentProvisioningModal
    :open="showProvisioningModal"
    :deployment="deploymentEntry"
    @close="showProvisioningModal = false"
  />
  <PageContainer v-if="!deploymentEntryIsError">
    <Button
      icon="arrow-left"
      hierarchy="link-color"
      class="w-min"
      :as="RouterLink"
      :to="{ name: 'deployments' }"
    >
      {{ t('layouts.single-page.go-back') }}
    </Button>
    <!-- Banner -->
    <div
      class="bg-warning-50 rounded-lg border border-gray-warm-300 grid gap-3 p-4 lg:px-5 lg:p-0 sm:grid-cols-2 md:grid-cols-[auto_1fr_auto] md:gap-8 md:px-7.5 overflow-hidden"
    >
      <img
        :src="bannerDeployments"
        :alt="t('views.deployment.banner.alt')"
        class="max-h-32 mb-0 hidden lg:block"
      />
      <div class="flex flex-col justify-between gap-2 md:mt-5 md:mb-5 md:gap-0">
        <Badge v-bind="visibilityBadgeClass" class="w-fit" />
        <Skeleton v-if="deploymentEntryIsPending" class="h-5 w-40" />
        <h2 v-else class="text-lg font-bold">{{ deploymentEntry?.info.name }}</h2>
      </div>
      <dl class="grid gap-2 grid-cols-3 w-fit m-auto md:w-full xl:gap-8 items-center">
        <div
          class="flex flex-col items-center bg-base-white border border-gray-warm-300 rounded-lg gap-1.5 p-2 md:gap-4 md:pr-3 md:flex-row xl:p-4.5 xl:pr-5 xl:min-w-43.75"
        >
          <div class="rounded-full bg-base-menu p-3">
            <Icon name="user-03" stroke-color="warm-500" :size="isXL ? 'xl' : 'sm'" />
          </div>
          <div>
            <dt class="text-xs text-gray-warm-800">
              {{ t('views.deployment.banner.users') }}
            </dt>
            <Skeleton v-if="deploymentEntryIsPending" class="h-5 w-10 mt-2" />
            <dd v-else class="text-xl font-bold text-center md:text-left">
              {{ deploymentEntry?.info.total_users }}
            </dd>
          </div>
        </div>
        <div
          class="flex flex-col items-center bg-base-white border border-gray-warm-300 rounded-lg gap-1.5 p-2 md:gap-4 md:pr-3 md:flex-row xl:p-4.5 xl:pr-5 xl:min-w-43.75"
        >
          <div class="rounded-full bg-base-menu p-3">
            <Icon name="power-01" stroke-color="warm-500" :size="isXL ? 'xl' : 'sm'" />
          </div>
          <div>
            <dt class="text-xs text-gray-warm-800">
              {{ t('views.deployment.banner.started') }}
            </dt>
            <Skeleton v-if="deploymentEntryIsPending" class="h-5 w-10 mt-2" />
            <dd v-else class="text-xl font-bold text-center md:text-left">
              {{ deploymentEntry?.info.started_desktops }}
            </dd>
          </div>
        </div>
        <div
          class="flex flex-col items-center bg-base-white border border-gray-warm-300 rounded-lg gap-1.5 p-2 md:gap-4 md:pr-3 md:flex-row xl:p-4.5 xl:pr-5 xl:min-w-43.75"
        >
          <div class="rounded-full bg-base-menu p-3">
            <Icon name="eye" stroke-color="warm-500" :size="isXL ? 'xl' : 'sm'" />
          </div>
          <div>
            <dt class="text-xs text-gray-warm-800">
              {{ t('views.deployment.banner.visible') }}
            </dt>
            <Skeleton v-if="deploymentEntryIsPending" class="h-5 w-10 mt-2" />
            <dd v-else class="text-xl font-bold text-center md:text-left">
              {{ deploymentEntry?.info.visible_desktops }}
            </dd>
          </div>
        </div>
      </dl>
    </div>
    <PageToolbar>
      <template v-if="hasDeploymentUsers" #search>
        <SearchInput
          :id="DEPLOYMENT_SEARCH_INPUT_ID"
          v-model="inputSearch"
          :placeholder="t('views.deployment.search-placeholder')"
        />
      </template>
      <template #actions>
        <Button icon="users-01" hierarchy="secondary-gray" @click="openAllowedModal">
          {{ t('views.deployment.buttons.users-and-groups') }}
        </Button>
        <Button icon="tv-03" hierarchy="secondary-gray" @click="enterVideowall">
          {{ t('views.deployment.buttons.videowall') }}
        </Button>
        <Button icon="stop" hierarchy="destructive" @click="handleNotImplemented">
          {{ t('views.deployment.buttons.stop-all') }}
        </Button>
        <DropdownMenu>
          <span @click.stop>
            <DropdownMenuTrigger>
              <Button
                hierarchy="secondary-gray"
                icon="dots-vertical"
                class="aspect-square p-[10px]"
              />
            </DropdownMenuTrigger>
          </span>
          <DropdownMenuContent class="bg-white border border-gray-warm-300 rounded-lg" align="end">
            <DropdownMenuGroup>
              <DropdownMenuItem
                v-for="action in dropdownActions"
                :key="action.key"
                :class="{ 'hover:bg-error-50 focus:bg-error-50': action.destructive }"
                :disabled="action.disabled"
                @click="action.fn(deploymentEntry?.info)"
              >
                <Button
                  size="sm"
                  class="mr-2 w-full justify-start"
                  :class="{ 'text-error-700': action.destructive }"
                  hierarchy="link-gray"
                  :icon="action.icon"
                  icon-size="md"
                  :disabled="action.disabled"
                >
                  {{ action.label }}
                </Button>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </template>
    </PageToolbar>
    <div v-if="deploymentEntryIsPending" class="flex flex-col gap-4">
      <div v-for="n in 4" :key="'skeleton-row-' + n">
        <Skeleton class="h-16 w-full rounded-r-2xl" />
      </div>
    </div>
    <template v-else-if="filteredDeploymentUsers.length > 0">
      <DataTable
        :rows="filteredDeploymentUsers"
        :headers="header"
        cell-class="h-19"
        :is-clickable="false"
      >
        <template #cell-visible>
          <Switch @update:model-value="handleNotImplemented" />
        </template>
        <template #cell-last_access="{ row }">
          <Tooltip v-if="row.last_access">
            <TooltipTrigger as-child>
              <span>
                {{
                  d(row.last_access * 1000, { dateStyle: 'short' }) +
                  ', ' +
                  d(row.last_access * 1000, { timeStyle: 'medium' })
                }}
              </span>
            </TooltipTrigger>
            <TooltipContent :title="formatRelativeTime(row.last_access, locale)" />
          </Tooltip>
          <span v-else>—</span>
        </template>
        <template #cell-name="{ row }">
          <div class="flex items-center gap-2">
            <AvatarLabel
              :src="row.photo"
              :name="row.name"
              :name-class="row.active === false ? 'text-gray-warm-400' : ''"
            />
            <Tooltip v-if="row.active === false">
              <TooltipTrigger as-child>
                <Badge
                  color="gray"
                  shape="square"
                  size="sm"
                  icon="slash-circle-01"
                  class="w-fit gap-1.5"
                  :content="t('views.deployment.data-table.disabled-user.badge')"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('views.deployment.data-table.disabled-user.tooltip')" />
            </Tooltip>
          </div>
        </template>
        <template #cell-started_desktops="{ row }">
          <div
            class="flex justify-center w-full text-sm font-medium tracking-widest text-gray-warm-900"
          >
            {{
              row.desktops_statuses.find((d) => d.status === DesktopStatusEnum.STARTED)?.amount ??
              0
            }}/{{ totalDesktops }}
          </div>
        </template>
        <template #cell-actions="{ row }">
          <div class="flex justify-between w-full gap-6">
            <div class="flex gap-4">
              <Button
                icon="arrow-circle-broken-right"
                hierarchy="secondary-color"
                :as="RouterLink"
                :to="{
                  name: 'view-deployment',
                  params: {
                    deploymentId: row.deployment_id,
                    userId: row.id
                  }
                }"
              >
                {{ t('views.deployment.buttons.enter') }}
              </Button>
              <Button
                v-if="row.desktops_statuses.some((s) => s.status === DesktopStatusEnum.STARTED)"
                icon="stop"
                hierarchy="destructive"
                @click="handleNotImplemented"
              >
                {{ t('views.deployment.buttons.stop') }}
              </Button>
            </div>
            <div class="flex items-center justify-end w-fit h-full gap-6">
              <Tooltip>
                <TooltipTrigger as-child>
                  <!-- Button is active if at least one desktop status is STARTED, STOPPING, or SHUTTING_DOWN -->
                  <Button
                    hierarchy="secondary-gray"
                    icon="tv-03"
                    class="aspect-square p-[10px]"
                    :disabled="
                      !row.desktops_statuses.some((s) =>
                        [
                          DesktopStatusEnum.STARTED,
                          DesktopStatusEnum.STOPPING,
                          DesktopStatusEnum.SHUTTING_DOWN
                        ].includes(s.status)
                      )
                    "
                    @click="enterVideowall"
                  ></Button>
                </TooltipTrigger>
                <TooltipContent side="top" :title="t('views.deployment.tooltips.videowall')" />
              </Tooltip>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    hierarchy="secondary-gray"
                    icon="file-attachment-04"
                    class="aspect-square p-[10px]"
                    @click="handleNotImplemented"
                  ></Button>
                </TooltipTrigger>
                <TooltipContent :side="'top'" :title="t('views.deployment.tooltips.resources')" />
              </Tooltip>
              <Tooltip v-if="canUseBastion">
                <TooltipTrigger as-child>
                  <Button
                    hierarchy="secondary-gray"
                    icon="globe-04"
                    class="aspect-square p-[10px]"
                    :aria-label="t('views.deployment.tooltips.bastion')"
                    @click="bastionUserModalData = { userId: row.id, username: row.name }"
                  ></Button>
                </TooltipTrigger>
                <TooltipContent :side="'top'" :title="t('views.deployment.tooltips.bastion')" />
              </Tooltip>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    hierarchy="secondary-gray"
                    icon="trash-04"
                    class="aspect-square p-[10px]"
                    @click="handleNotImplemented"
                  ></Button>
                </TooltipTrigger>
                <TooltipContent :side="'top'" :title="t('views.deployment.tooltips.delete')" />
              </Tooltip>
            </div>
          </div>
        </template>
      </DataTable>
    </template>
    <EmptyState
      v-else
      kind="deployment-users"
      :variant="hasDeploymentUsers ? 'no-results' : 'first-run'"
      :searching="inputSearch.length > 0"
      @clear-search="inputSearch = ''"
    />
  </PageContainer>
</template>
