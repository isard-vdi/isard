<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import DataTable from '@/components/data-table/DataTable.vue'
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import {
  getAllDeploymentsOptions,
  checkQuotaNewDeploymentOptions,
  editDeploymentUsersMutation,
  getDeploymentAllowedQueryKey,
  getDeploymentCoOwnersOptions,
  getDeploymentCoOwnersQueryKey,
  updateDeploymentCoOwnersMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { type ErrorResponse, type OwnedDeployment } from '@/gen/oas/apiv4'
import { QuotaExceededModal } from '@/components/modal'
import { AllowedModal, type AllowedOption, type AllowedSelection } from '@/components/modal/allowed'
import { toast } from '@/components/ui/toast'
import { DeleteModal } from '@/components/deployments/actions/delete-modal'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import Badge from '@/components/badge/Badge.vue'
import BadgeInfo from '@/components/badge/info/BadgeInfo.vue'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useRoute, useRouter } from 'vue-router'
import { cn } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { RecreateModal } from '@/components/deployments/actions/recreate-modal'
import { DownloadCsvModal } from '@/components/deployments/actions/download-csv-modal'
import {
  EmptyState,
  FilterPanel,
  FilterToggle,
  PageContainer,
  PageToolbar,
  SearchInput
} from '@/components/page'
import { useFilterPanel } from '@/composables/useFilterPanel'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const queryClient = useQueryClient()

// Queries
const {
  isPending: deploymentsArePending,
  isError: deploymentsIsError,
  error: deploymentsError,
  data: deployments
} = useQuery(getAllDeploymentsOptions())

// New deployments quota check
const showQuotaExceededModal = ref(false)
const checkQuotaIsPending = ref(false)

const goToNewDeployment = async () => {
  checkQuotaIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewDeploymentOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    checkQuotaIsPending.value = false
    router.push({ name: 'new-deployment' })
  } catch {
    checkQuotaIsPending.value = false
    showQuotaExceededModal.value = true
  }
}

// Filters
interface DeploymentFilters {
  status: 'all' | 'visible' | 'hidden'
}

const deploymentFilters = ref<DeploymentFilters>({ status: 'all' })

const showDeploymentFilters = useFilterPanel('deployments_filters_state')

// Search has its own always-visible input; only the ones the panel hides count.
const activeDeploymentFilterCount = computed(() =>
  deploymentFilters.value.status === 'all' ? 0 : 1
)

const filteredDeployments = computed(() => {
  const allDeployments = deployments.value?.deployments ?? []
  return allDeployments.filter(areDeploymentsVisible)
})

// Visibility
const areDeploymentsVisible = (deployments: OwnedDeployment) => {
  //  Search filter
  const matchesSearch =
    inputSearch.value.toLowerCase() === '' ||
    deployments.name.toLowerCase().includes(inputSearch.value.toLowerCase()) ||
    deployments.description?.toLowerCase().includes(inputSearch.value.toLowerCase())

  // Visibility filter
  const matchesVisibility =
    deploymentFilters.value.status === 'all' ||
    (deploymentFilters.value.status === 'visible' && deployments.tag_visible === true) ||
    (deploymentFilters.value.status === 'hidden' && deployments.tag_visible !== true)

  return matchesSearch && matchesVisibility
}

const inputSearch = ref<string>('')

// Data Table Header
const header = computed(() => [
  {
    key: 'tag_visible',
    name: t('views.deployments.data-table.headers.visibility'),
    sortable: true,
    width: 'max-content'
  },
  {
    key: 'name',
    name: t('views.deployments.data-table.headers.name'),
    sortable: true
  },
  {
    key: 'description',
    name: t('views.deployments.data-table.headers.description'),
    sortable: true
  },
  {
    key: 'started_desktops',
    name: t('views.deployments.data-table.headers.started-desktops'),
    sortable: true,
    width: 'minmax(max-content, 120px)'
  },
  {
    key: 'visible_desktops',
    name: t('views.deployments.data-table.headers.visible-desktops'),
    sortable: true,
    width: 'minmax(max-content, 120px)'
  },
  {
    key: 'total_users',
    name: t('views.deployments.data-table.headers.total-users'),
    sortable: true,
    width: 'minmax(max-content, 120px)'
  },
  {
    key: 'dropdown_menu',
    name: '',
    sortable: false,
    width: 'max-content'
  }
])

// Unfiltered count, to tell a first run from a fruitless search.
const totalDeployments = computed(() => deployments.value?.deployments?.length ?? 0)

const isFirstRun = computed(() => !deploymentsArePending.value && totalDeployments.value === 0)

const clearDeploymentFilters = () => {
  deploymentFilters.value.status = 'all'
}

const badgeState = (isVisible: boolean) => ({
  color: isVisible ? 'blue' : ('gray' as const),
  content: isVisible
    ? t('views.deployments.visibility.visible')
    : t('views.deployments.visibility.hidden'),
  icon: isVisible ? 'eye' : 'eye-off',
  shape: 'square' as const,
  class: 'gap-2'
})

interface DeploymentAction {
  key: string
  icon: string
  label: string
  destructive?: boolean
  disabledFor?: (deployment: OwnedDeployment) => boolean
  disabledTooltip?: string
  hiddenFor?: (deployment: OwnedDeployment) => boolean
  fn: (deployment: OwnedDeployment) => void
}

const dropdownActions = computed<DeploymentAction[]>(() => [
  {
    key: 'edit',
    icon: 'edit-01',
    label: t('views.deployments.dropdown.buttons.edit'),
    fn: handleNotImplemented
  },
  {
    key: 'alloweds',
    icon: 'users-01',
    label: t('views.deployments.dropdown.buttons.alloweds'),
    fn: (deployment: OwnedDeployment) => {
      allowedError.value = ''
      allowedModalDeploymentId.value = deployment.id
    }
  },
  {
    key: 'co-owners',
    icon: 'users-plus',
    label: t('views.deployments.dropdown.buttons.co-owners'),
    fn: (deployment: OwnedDeployment) => {
      coOwnersError.value = ''
      coOwnersModalDeploymentData.value = {
        id: deployment.id,
        name: deployment.name,
        coOwner: deployment.co_owner
      }
    }
  },
  {
    key: 'download',
    icon: 'download-02',
    label: t('views.deployments.dropdown.buttons.download-viewer'),
    fn: (deployment: OwnedDeployment) => {
      downloadCsvModalDeploymentData.value = { id: deployment.id, name: deployment.name }
      showDownloadCsvModal.value = true
    }
  },
  {
    key: 'recreate',
    icon: 'refresh-cw-04',
    label: t('views.deployments.dropdown.buttons.recreate'),
    fn: (deployment: OwnedDeployment) => {
      recreateModalDeploymentData.value = { id: deployment.id, name: deployment.name }
      showRecreateModal.value = true
    }
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
    hiddenFor: (deployment: OwnedDeployment) => deployment.co_owner,
    fn: (deployment: OwnedDeployment) =>
      (deleteModalDeploymentData.value = { id: deployment.id, name: deployment.name })
  }
])

const handleNotImplemented = () => alert('not implemented yet')

const showDeleteModal = computed(() => deleteModalDeploymentData.value !== null)
const deleteModalDeploymentData = ref<{
  id: string
  name: string
} | null>(null)

const closeDeleteModal = () => {
  deleteModalDeploymentData.value = null
}

const showRecreateModal = ref(false)
const recreateModalDeploymentData = ref<{
  id: string
  name: string
} | null>(null)

const closeRecreateModal = () => (showRecreateModal.value = false)

const showDownloadCsvModal = ref(false)
const downloadCsvModalDeploymentData = ref<{
  id: string
  name: string
} | null>(null)

const visibleDropdownActions = (deployment: OwnedDeployment) =>
  dropdownActions.value.filter((action) => !action.hiddenFor?.(deployment))

const coOwnersModalDeploymentData = ref<{ id: string; name: string; coOwner: boolean } | null>(null)
const coOwnersDeploymentId = computed(() => coOwnersModalDeploymentData.value?.id ?? '')
const coOwnersError = ref('')

const { data: coOwners } = useQuery({
  ...getDeploymentCoOwnersOptions({ path: { deployment_id: coOwnersDeploymentId.value } }),
  queryKey: computed(() =>
    getDeploymentCoOwnersQueryKey({ path: { deployment_id: coOwnersDeploymentId.value } })
  ),
  enabled: computed(() => !!coOwnersDeploymentId.value)
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

const closeCoOwnersModal = () => {
  coOwnersModalDeploymentData.value = null
  coOwnersError.value = ''
}

const handleSaveCoOwners = (selection: AllowedSelection) => {
  const deploymentId = coOwnersDeploymentId.value
  if (!deploymentId) return
  coOwnersError.value = ''
  updateCoOwners({
    path: { deployment_id: deploymentId },
    body: { co_owners: Array.isArray(selection.users) ? selection.users : [] }
  })
}

const allowedModalDeploymentId = ref<string | null>(null)
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

const closeAllowedModal = () => {
  allowedModalDeploymentId.value = null
  allowedError.value = ''
}

const handleSaveAllowed = (selection: AllowedSelection) => {
  const deploymentId = allowedModalDeploymentId.value
  if (!deploymentId) return
  allowedError.value = ''
  editDeploymentUsers({ path: { deployment_id: deploymentId }, body: { allowed: selection } })
}

const goToDeployment = (row: any) => {
  if (!row?.id) return
  router.push({ name: 'deployment', params: { deploymentId: row.id } })
}

const DEPLOYMENTS_SEARCH_INPUT_ID = 'deployments-search'
</script>

<template>
  <QuotaExceededModal
    :open="showQuotaExceededModal"
    :title="t('components.deployments.quota-exceeded-modal.title')"
    :description="t('components.deployments.quota-exceeded-modal.description')"
    :cancel-label="t('components.deployments.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'deployments' }"
    @close="showQuotaExceededModal = false"
  />
  <AllowedModal
    v-if="allowedModalDeploymentId"
    open
    item-type="deployment"
    :item-id="allowedModalDeploymentId"
    :warning="t('views.deployments.alloweds.warning')"
    require-selection
    :supports-everyone="false"
    :loading="updateAllowedIsPending"
    :error="allowedError"
    @save="handleSaveAllowed"
    @close="closeAllowedModal"
  />
  <AllowedModal
    v-if="coOwnersModalDeploymentData"
    open
    users-only
    :roles="['advanced', 'manager', 'admin']"
    :supports-everyone="false"
    :selection="coOwnersSelection"
    :preselected-users="preselectedCoOwners"
    :title="
      t('components.deployments.co-owners-modal.title', {
        name: coOwnersModalDeploymentData.name
      })
    "
    :description="
      t('components.deployments.co-owners-modal.description', { owner: coOwnersOwnerName })
    "
    :readonly="coOwnersModalDeploymentData.coOwner"
    :warning="
      t(
        coOwnersModalDeploymentData.coOwner
          ? 'components.deployments.co-owners-modal.co-owner-warning'
          : 'components.deployments.co-owners-modal.warning'
      )
    "
    :loading="updateCoOwnersIsPending"
    :error="coOwnersError"
    @save="handleSaveCoOwners"
    @close="closeCoOwnersModal"
  />
  <RecreateModal
    :open="showRecreateModal"
    :deployment-id="recreateModalDeploymentData?.id || ''"
    :deployment-name="recreateModalDeploymentData?.name"
    :onSuccess="closeRecreateModal"
    @close="closeRecreateModal"
  />
  <DownloadCsvModal
    v-model:open="showDownloadCsvModal"
    :deployment-id="downloadCsvModalDeploymentData?.id || ''"
    :deployment-name="downloadCsvModalDeploymentData?.name || ''"
  />
  <DeleteModal
    :open="showDeleteModal"
    :deployment-id="deleteModalDeploymentData?.id || ''"
    :deployment-name="deleteModalDeploymentData?.name"
    :on-success="closeDeleteModal"
    @close="closeDeleteModal"
  />
  <PageContainer>
    <div v-if="deploymentsIsError" class="text-center text-error-500">
      <pre>{{ deploymentsError }}</pre>
    </div>
    <PageToolbar v-if="!isFirstRun">
      <template #search>
        <SearchInput
          :id="DEPLOYMENTS_SEARCH_INPUT_ID"
          v-model="inputSearch"
          :placeholder="t('views.deployments.filters.search.placeholder')"
        />
      </template>
      <template #filters>
        <FilterToggle v-model="showDeploymentFilters" :active-count="activeDeploymentFilterCount" />
      </template>
      <template #actions>
        <Button
          :disabled="checkQuotaIsPending"
          :icon="checkQuotaIsPending ? 'loading-02' : 'plus'"
          :icon-class="cn(checkQuotaIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')"
          @click="goToNewDeployment"
        >
          {{ t('router.deployments.new.title') }}
        </Button>
      </template>
      <template #panel>
        <FilterPanel :open="showDeploymentFilters">
          <ToggleGroup
            v-model="deploymentFilters.status"
            :spacing="1"
            type="single"
            size="default"
            class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg"
          >
            <ToggleGroupItem value="all" variant="gray-warm">
              <span>{{ t('views.deployments.filters.status.all') }}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="visible" variant="gray-warm">
              <span>{{ t('views.deployments.filters.status.visible') }}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="hidden" variant="gray-warm">
              <span>{{ t('views.deployments.filters.status.hidden') }}</span>
            </ToggleGroupItem>
          </ToggleGroup>
        </FilterPanel>
      </template>
    </PageToolbar>
    <div v-if="deploymentsArePending" class="flex flex-col gap-4 mt-8">
      <div v-for="n in 4" :key="'skeleton-row-' + n">
        <Skeleton class="h-16 w-full rounded-r-2xl" />
      </div>
    </div>
    <template v-else-if="filteredDeployments.length > 0">
      <DataTable
        :headers="header"
        :rows="filteredDeployments"
        :is-clickable="true"
        row-class="hover:bg-brand-100"
        cell-class="h-19"
        @row-click="goToDeployment"
      >
        <template #cell-tag_visible="{ row }">
          <Badge v-bind="badgeState(row.tag_visible)" />
        </template>
        <template #cell-name="{ row }">
          <div class="text-sm font-semibold">{{ row.name }}</div>
        </template>
        <template #cell-description="{ row }">
          <div class="text-xs font-medium text-gray-warm-600 pr-2 line-clamp-2">
            {{ row.description }}
          </div>
        </template>
        <template #cell-started_desktops="{ row }">
          <BadgeInfo icon="power-01" :content="row.started_desktops" />
        </template>
        <template #cell-visible_desktops="{ row }">
          <BadgeInfo icon="eye" :content="row.visible_desktops" />
        </template>
        <template #cell-total_users="{ row }">
          <BadgeInfo icon="user-03" :content="row.total_users" />
        </template>
        <template #cell-dropdown_menu="{ row }">
          <Tooltip>
            <TooltipTrigger as-child>
              <span class="inline-flex" @click.stop @keydown.enter.stop @keydown.space.stop>
                <DropdownMenu>
                  <DropdownMenuTrigger>
                    <Button
                      hierarchy="secondary-gray"
                      icon="dots-vertical"
                      class="aspect-square p-[10px]"
                    />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    class="bg-white border border-gray-warm-300 rounded-lg"
                    align="end"
                  >
                    <DropdownMenuGroup>
                      <DropdownMenuItem
                        v-for="action in visibleDropdownActions(row)"
                        :key="action.key"
                        :class="{ 'hover:bg-error-50 focus:bg-error-50': action.destructive }"
                        @click="action.fn(row)"
                      >
                        <Button
                          size="sm"
                          class="mr-2 w-full justify-start"
                          :class="{ 'text-error-700': action.destructive }"
                          hierarchy="link-gray"
                          :icon="action.icon"
                          icon-size="md"
                        >
                          {{ action.label }}
                        </Button>
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              </span>
            </TooltipTrigger>
            <TooltipContent :title="t('common.actions.more')" />
          </Tooltip>
        </template>
      </DataTable>
    </template>
    <EmptyState
      v-else
      kind="deployments"
      :variant="isFirstRun ? 'first-run' : 'no-results'"
      :searching="inputSearch.length > 0"
      :active-filters="activeDeploymentFilterCount"
      @clear-search="inputSearch = ''"
      @clear-filters="clearDeploymentFilters"
    >
      <template v-if="isFirstRun" #actions>
        <Button
          :disabled="checkQuotaIsPending"
          :icon="checkQuotaIsPending ? 'loading-02' : 'plus'"
          :icon-class="cn(checkQuotaIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')"
          size="lg"
          @click="goToNewDeployment"
        >
          {{ t('router.deployments.new.title') }}
        </Button>
      </template>
    </EmptyState>
  </PageContainer>
</template>
