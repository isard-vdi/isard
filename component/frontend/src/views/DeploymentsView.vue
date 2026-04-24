<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import DataTable from '@/components/data-table/DataTable.vue'
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import {
  getAllDeploymentsApiV4ItemsDeploymentsGetOptions,
  checkQuotaNewDeploymentApiV4QuotaDeploymentNewGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { type OwnedDeployment } from '@/gen/oas/apiv4'
import InputField from '@/components/input-field/InputField.vue'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty'
import { QuotaExceededModal } from '@/components/modal'
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
import desktopsEmptyImg from '@/assets/img/desktops-empty.svg'
import templatesEmptyImg from '@/assets/img/templates-empty.svg'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useRoute, useRouter } from 'vue-router'
import { cn } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import Icon from '@/components/icon/Icon.vue'
import { RecreateModal } from '@/components/deployments/actions/recreate-modal'
import { DownloadCsvModal } from '@/components/deployments/actions/download-csv-modal'

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
} = useQuery(getAllDeploymentsApiV4ItemsDeploymentsGetOptions())

// New deployments quota check
const showQuotaExceededModal = ref(false)
const checkQuotaIsPending = ref(false)

const goToNewDeployment = async () => {
  checkQuotaIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewDeploymentApiV4QuotaDeploymentNewGetOptions(),
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
  status: 'all' | 'visible'
}

const deploymentFilters = ref<DeploymentFilters>({ status: 'all' })

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
    (deploymentFilters.value.status === 'visible' && deployments.tag_visible === true)

  return matchesSearch && matchesVisibility
}

const inputSearch = ref<string>('')

// Data Table Header
const header = computed(() => [
  {
    key: 'tag_visible',
    name: t('views.deployments.data-table.headers.visibility'),
    sortable: true,
    width: 'minmax(150px, max-content)'
  },
  {
    key: 'name',
    name: t('views.deployments.data-table.headers.name'),
    sortable: true,
    width: 'minmax(300px, 1fr)'
  },
  {
    key: 'description',
    name: t('views.deployments.data-table.headers.description'),
    sortable: true,
    width: 'minmax(300px, 1fr)'
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
    width: 'minmax(max-content, 120px)'
  }
])

const emptyState = computed(() => {
  const isSearching = inputSearch.value.length > 0

  return {
    title: isSearching
      ? t('components.empty-search.title')
      : t('components.empty.title', { kind: t('domains.deployments', 0) }),
    subtitle: isSearching ? undefined : t('views.deployments.empty.subtitle'),
    image: isSearching ? templatesEmptyImg : desktopsEmptyImg,
    styles: isSearching ? 'md:flex-row-reverse mt-16' : ''
  }
})

const badgeState = (isVisible: boolean) => ({
  color: isVisible ? 'blue' : ('gray' as const),
  content: isVisible
    ? t('views.deployments.visibility.visible')
    : t('views.deployments.visibility.hidden'),
  icon: isVisible ? 'eye' : 'eye-off',
  shape: 'square' as const,
  class: 'gap-2'
})

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

const goToDeployment = (row: any) => {
  if (!row?.id) return
  router.push({ name: 'deployment', params: { deploymentId: row.id } })
}
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
  <div v-if="deploymentsIsError" class="text-center text-error-500">
    <pre>{{ deploymentsError }}</pre>
  </div>
  <main class="flex flex-col gap-6 p-4 w-full max-w-420 m-auto">
    <div class="flex flex-row-reverse justify-end gap-2">
      <p class="text-3xl font-bold">{{ t('views.deployments.table-title') }}</p>
      <Icon name="info-circle" />
    </div>
    <div class="flex justify-between w-full items-center">
      <InputField
        v-model="inputSearch"
        :placeholder="t('views.deployments.filters.search.placeholder')"
        icon="search-lg"
        class="h-min w-full max-w-120 mr-auto"
      />
      <div class="flex flex-row gap-5 items-center flex-wrap">
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
        </ToggleGroup>
        <Button
          :disabled="checkQuotaIsPending"
          :icon="checkQuotaIsPending ? 'loading-02' : 'plus'"
          :icon-class="cn(checkQuotaIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')"
          @click="goToNewDeployment"
        >
          {{ t('router.deployments.new.title') }}
        </Button>
      </div>
    </div>
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
          <DropdownMenu>
            <span @click.stop @keydown.enter.stop @keydown.space.stop>
              <DropdownMenuTrigger>
                <Button
                  hierarchy="secondary-gray"
                  icon="dots-vertical"
                  class="aspect-square p-[10px]"
                />
              </DropdownMenuTrigger>
            </span>
            <DropdownMenuContent
              class="bg-white border border-gray-warm-300 rounded-lg"
              align="end"
            >
              <DropdownMenuGroup>
                <DropdownMenuItem
                  v-for="action in dropdownActions"
                  :key="action.key"
                  :class="{ 'hover:bg-red-50 focus:bg-red-50': action.destructive }"
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
        </template>
      </DataTable>
    </template>
    <template v-else>
      <Empty :class="emptyState.styles">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none">
            <img :src="emptyState.image" />
          </EmptyMedia>
        </EmptyHeader>
        <EmptyTitle class="text-[30px] font-bold">
          {{ emptyState.title }}
        </EmptyTitle>
        <EmptyDescription class="text-[18px]!">
          {{ emptyState.subtitle }}
        </EmptyDescription>
      </Empty>
    </template>
  </main>
</template>
