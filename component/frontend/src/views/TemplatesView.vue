<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'

import {
  getUserTemplatesOptions,
  getUserSharedTemplatesOptions,
  checkQuotaNewTemplateOptions,
  updateTemplateAllowedMutation,
  getTemplateAllowedQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { copyToClipboard } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { canCreateAnyDesktop } from '@/lib/quotas'
import { useUserStore } from '@/stores/user'

import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem
} from '@/components/ui/context-menu'
import { TemplateDataTable } from '@/components/data-table'
import {
  EmptyState,
  FilterPanel,
  FilterToggle,
  PageContainer,
  PageToolbar,
  SearchInput
} from '@/components/page'
import { useFilterPanel } from '@/composables/useFilterPanel'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/icon'
import { QuotaExceededModal } from '@/components/modal'
import { AllowedModal, type AllowedSelection } from '@/components/modal/allowed'
import { TemplateDeleteModal } from '@/components/templates/template-delete-modal'
import { TemplateToDesktopModal } from '@/components/templates/template-to-desktop-modal'
import { TemplateToggleVisibilityModal } from '@/components/template-toggle-visibility'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { toggleVariants } from '@/components/ui/toggle'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toast'
import { DomainInfoModal } from '@/components/desktops'
import { getTemplateDetails } from '@/gen/oas/apiv4/'

const router = useRouter()
const queryClient = useQueryClient()
const userStore = useUserStore()
const { t } = useI18n()

const activeTab = ref<'user' | 'shared'>('user')

const TEMPLATES_SEARCH_INPUT_ID = 'templates-search'
const inputSearch = ref('')

const showTemplateFilters = useFilterPanel('templates_filters_state')
const templateVisibility = ref<'all' | 'visible' | 'hidden'>('all')

// Search has its own always-visible input; only the ones the panel hides count.
const activeTemplateFilterCount = computed(() => (templateVisibility.value === 'all' ? 0 : 1))

// Queries
const {
  isPending: userTemplatesIsPending,
  isError: userTemplatesIsError,
  error: userTemplatesError,
  data: userTemplates
} = useQuery(getUserTemplatesOptions())

const {
  isFetching: sharedTemplatesIsFetching,
  isError: sharedTemplatesIsError,
  error: sharedTemplatesError,
  data: sharedTemplates,
  refetch: fetchSharedTemplates
} = useQuery({
  ...getUserSharedTemplatesOptions(),
  enabled: false // Lazy load when tab is clicked
})

// Table configuration
const tableHeaders = computed(() => {
  const baseHeaders = [
    { name: '', key: 'image', width: 'var(--spacing-48)' },
    {
      name: t('views.templates.table.headers.name'),
      key: 'name',
      width: 'minmax(var(--spacing-48), var(--spacing-80))'
    },
    {
      name: t('views.templates.table.headers.description'),
      key: 'description',
      width: 'minmax(var(--spacing-56), 1fr)'
    }
  ]

  if (activeTab.value === 'shared') {
    baseHeaders.push({
      name: t('views.templates.table.headers.owner'),
      key: 'owner',
      width: 'minmax(var(--spacing-48), var(--spacing-64))'
    })
  }

  baseHeaders.push({ name: '', key: 'actions', width: 'max-content' })
  return baseHeaders
})

const tableRows = computed(() => {
  // Only owned templates carry a visibility flag, so the filter is theirs alone.
  if (activeTab.value === 'shared') {
    return sharedTemplates.value?.templates || []
  }

  return (userTemplates.value?.templates || []).filter((template) => {
    if (templateVisibility.value === 'all') {
      return true
    }

    // Legacy rows come back without the field and are visible
    const isVisible = template.enabled !== false
    return templateVisibility.value === 'visible' ? isVisible : !isVisible
  })
})

// Unfiltered count of the active tab, to tell a first run from a fruitless search.
const totalTemplates = computed(() =>
  activeTab.value === 'shared'
    ? (sharedTemplates.value?.templates?.length ?? 0)
    : (userTemplates.value?.templates?.length ?? 0)
)

// The shared tab loads lazily, so an unfetched cache still counts as pending.
const templatesArePending = computed(() =>
  activeTab.value === 'shared'
    ? sharedTemplatesIsFetching.value || !sharedTemplates.value
    : userTemplatesIsPending.value
)

const isFirstRun = computed(() => !templatesArePending.value && totalTemplates.value === 0)

const emptyKind = computed(() => (activeTab.value === 'shared' ? 'shared-templates' : 'templates'))

const handleSharedTabClick = () => {
  if (!sharedTemplates.value) {
    fetchSharedTemplates()
  }
}

// Modal state - unified structure
interface ModalData {
  id: string
  name: string
}

const deleteModalData = ref<ModalData | null>(null)
const convertModalData = ref<ModalData | null>(null)
const visibilityModalData = ref<(ModalData & { action: 'hide' | 'show' }) | null>(null)
const allowedModalData = ref<ModalData | null>(null)
const allowedError = ref('')

// Quota check
const quotaExceededModalData = ref<{
  title: string
  description: string
  cancelLabel: string
} | null>(null)
const templateCreationCheckIsPending = ref(false)
const desktopCreationCheckIsPending = ref(false)

const handleWithTemplateQuotaCheck = async (callback: () => void) => {
  templateCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewTemplateOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    templateCreationCheckIsPending.value = false
    callback()
  } catch {
    templateCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.templates.quota-exceeded-modal.title'),
      description: t('components.templates.quota-exceeded-modal.description'),
      cancelLabel: t('components.templates.quota-exceeded-modal.cancel')
    }
  }
}

const handleWithDesktopQuotaCheck = async (callback: () => void) => {
  desktopCreationCheckIsPending.value = true
  if (await canCreateAnyDesktop(queryClient, userStore.config?.show_temporal_tab !== false)) {
    desktopCreationCheckIsPending.value = false
    callback()
  } else {
    desktopCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.desktops.quota-exceeded-modal.title'),
      description: t('components.desktops.quota-exceeded-modal.description'),
      cancelLabel: t('components.desktops.quota-exceeded-modal.cancel')
    }
  }
}

// Template Info Modal
const showTemplateInfoModal = ref(false)
const {
  mutate: fetchTemplateDetails,
  isPending: fetchTemplateDetailsIsPending,
  isError: fetchTemplateDetailsIsError,
  error: fetchTemplateDetailsError,
  data: templateDetails,
  variables: templateDetailsDesktopId,
  reset: resetTemplateDetails
} = useMutation({
  mutationFn: async (templateId: string) => {
    const { data } = await getTemplateDetails({
      path: {
        template_id: templateId
      },
      throwOnError: true
    })
    return data
  }
})

const openTemplateInfoModal = (templateId: string) => {
  fetchTemplateDetails(templateId)
  showTemplateInfoModal.value = true
}

const { mutate: updateTemplateAllowed, isPending: updateAllowedIsPending } = useMutation({
  ...updateTemplateAllowedMutation(),
  onSuccess: (_data, variables) => {
    queryClient.removeQueries({
      queryKey: getTemplateAllowedQueryKey({
        path: { template_id: variables.path.template_id }
      })
    })
    closeAllowedModal()
    toast.success(t('views.templates.alloweds.success'))
  },
  onError: () => {
    allowedError.value = t('views.templates.alloweds.error')
  }
})

const openAllowedModal = (data: ModalData) => {
  allowedError.value = ''
  allowedModalData.value = data
}

const closeAllowedModal = () => {
  allowedModalData.value = null
  allowedError.value = ''
}

const handleSaveAllowed = (selection: AllowedSelection) => {
  const templateId = allowedModalData.value?.id
  if (!templateId) return
  allowedError.value = ''
  updateTemplateAllowed({ path: { template_id: templateId }, body: selection })
}

const isFailed = (row: Record<string, unknown>) => row.status === 'Failed'
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="!!quotaExceededModalData"
    :title="quotaExceededModalData?.title ?? ''"
    :description="quotaExceededModalData?.description ?? ''"
    :cancel-label="quotaExceededModalData?.cancelLabel ?? ''"
    :cancel-to="{ name: 'templates' }"
    @close="quotaExceededModalData = null"
  />

  <AllowedModal
    v-if="allowedModalData"
    open
    item-type="template"
    :item-id="allowedModalData.id"
    :loading="updateAllowedIsPending"
    :error="allowedError"
    @save="handleSaveAllowed"
    @close="closeAllowedModal"
  />

  <TemplateDeleteModal
    v-if="deleteModalData"
    :open="true"
    :template-id="deleteModalData.id"
    :template-name="deleteModalData.name"
    @close="deleteModalData = null"
  />

  <TemplateToDesktopModal
    v-if="convertModalData"
    :open="true"
    :template-id="convertModalData.id"
    :template-name="convertModalData.name"
    @close="convertModalData = null"
  />

  <TemplateToggleVisibilityModal
    v-if="visibilityModalData"
    :open="true"
    :action="visibilityModalData.action"
    :data="visibilityModalData"
    @close="visibilityModalData = null"
  />

  <DomainInfoModal
    :open="showTemplateInfoModal"
    :is-loading="fetchTemplateDetailsIsPending"
    :domain-id="templateDetailsDesktopId"
    :name="templateDetails?.name || ''"
    :description="templateDetails?.description"
    :vcpu="templateDetails?.vcpu"
    :ram="templateDetails?.memory"
    :boot-order="templateDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="templateDetails?.disk_bus?.name"
    :vga="templateDetails?.videos.map((vga) => vga.name)"
    :viewers="templateDetails?.viewers"
    :isos="templateDetails?.isos?.map((iso) => iso.name)"
    :reservables="templateDetails?.reservables?.vgpus"
    :credentials="templateDetails?.credentials"
    :kind="'template'"
    @close="
      () => {
        showTemplateInfoModal = false
        resetTemplateDetails()
      }
    "
  />

  <PageContainer>
    <div v-if="userTemplatesIsError || sharedTemplatesIsError" class="text-center text-error-500">
      <pre v-if="userTemplatesError">{{ userTemplatesError }}</pre>
      <pre v-if="sharedTemplatesError">{{ sharedTemplatesError }}</pre>
    </div>

    <PageToolbar>
      <template #tabs>
        <Tabs v-model="activeTab">
          <TabsList class="flex w-fit gap-[--spacing(1)] rounded-md">
            <TabsTrigger
              value="user"
              :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
            >
              <Icon name="user-03" stroke-color="currentColor" />
              {{ t('components.templates.template-type.owned') }}
            </TabsTrigger>
            <TabsTrigger
              value="shared"
              :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
              @click="handleSharedTabClick"
            >
              <Icon name="share-06" stroke-color="currentColor" />
              {{ t('components.templates.template-type.shared') }}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </template>

      <template v-if="!isFirstRun" #search>
        <SearchInput
          :id="TEMPLATES_SEARCH_INPUT_ID"
          v-model="inputSearch"
          :placeholder="t('views.templates.filters.search.placeholder')"
        />
      </template>

      <template v-if="!isFirstRun" #filters>
        <FilterToggle
          v-if="activeTab === 'user'"
          v-model="showTemplateFilters"
          :active-count="activeTemplateFilterCount"
        />
      </template>

      <template v-if="!isFirstRun" #actions>
        <Button
          :icon="templateCreationCheckIsPending ? 'loading-02' : 'plus'"
          :icon-class="{
            'motion-safe:animate-[spin_2s_linear_infinite]': templateCreationCheckIsPending
          }"
          :disabled="templateCreationCheckIsPending"
          @click="handleWithTemplateQuotaCheck(() => router.push({ name: 'new-template' }))"
          >{{ t('views.templates.new-template') }}</Button
        >
      </template>

      <template v-if="!isFirstRun" #panel>
        <FilterPanel :open="showTemplateFilters && activeTab === 'user'">
          <ToggleGroup
            v-model="templateVisibility"
            :spacing="1"
            type="single"
            size="default"
            class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg"
          >
            <ToggleGroupItem value="all" variant="gray-warm">
              <span>{{ t('views.templates.filters.visibility.all') }}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="visible" variant="gray-warm">
              <span>{{ t('views.templates.filters.visibility.visible') }}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="hidden" variant="gray-warm">
              <span>{{ t('views.templates.filters.visibility.hidden') }}</span>
            </ToggleGroupItem>
          </ToggleGroup>
        </FilterPanel>
      </template>
    </PageToolbar>

    <TemplateDataTable
      v-model:search="inputSearch"
      :headers="tableHeaders"
      :rows="tableRows"
      :total-rows="totalTemplates"
      :loading="templatesArePending"
      :is-clickable="false"
      hide-toolbar
    >
      <template #empty="{ variant }">
        <EmptyState
          :kind="emptyKind"
          :variant="variant"
          :searching="inputSearch.length > 0"
          :active-filters="activeTab === 'user' ? activeTemplateFilterCount : 0"
          @clear-search="inputSearch = ''"
          @clear-filters="templateVisibility = 'all'"
        >
          <template v-if="variant === 'first-run' && activeTab === 'user'" #actions>
            <Button
              :icon="templateCreationCheckIsPending ? 'loading-02' : 'plus'"
              :icon-class="{
                'motion-safe:animate-[spin_2s_linear_infinite]': templateCreationCheckIsPending
              }"
              :disabled="templateCreationCheckIsPending"
              size="lg"
              @click="handleWithTemplateQuotaCheck(() => router.push({ name: 'new-template' }))"
              >{{ t('views.templates.new-template') }}</Button
            >
          </template>
        </EmptyState>
      </template>

      <template #cell-image="{ row }">
        <div class="relative">
          <div
            class="w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover relative"
            :class="{ 'grayscale opacity-40': isFailed(row) }"
            :style="{
              backgroundImage: `url(${row.image.url})`
            }"
          >
            <ContextMenu>
              <ContextMenuTrigger class="absolute top-0 bottom-0 left-0 w-1/4 rounded-l-2xl">
              </ContextMenuTrigger>
              <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
                <ContextMenuItem @click="copyToClipboard(row.id)">{{
                  t('components.templates.datatable.debug-options.copy-id')
                }}</ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          </div>

          <Tooltip v-if="isFailed(row)">
            <TooltipTrigger as-child>
              <div
                aria-hidden="true"
                class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center bg-error-200/60 p-1.5 rounded-full backdrop-blur-xs border-2 border-base-white ring-[3px] ring-error-600/20 ring-offset-1 ring-offset-base-white/30 shadow-md shadow-error-700"
              >
                <Icon name="alert-triangle" size="xl" stroke-color="error-700" />
              </div>
            </TooltipTrigger>
            <TooltipContent :title="t('views.templates.table.failed-message')" />
          </Tooltip>
        </div>
      </template>

      <template #cell-name="{ row }">
        <div class="flex flex-col">
          <p class="text-sm font-semibold text-gray-warm-900 truncate">{{ row.name }}</p>
          <template v-if="isFailed(row)">
            <Tooltip :delay-duration="200">
              <TooltipTrigger as-child>
                <div
                  class="inline-flex items-center gap-1.5 font-semibold max-w-full w-max text-xs text-error-600"
                >
                  <span aria-hidden="true" class="contents">
                    <Icon
                      name="info-circle"
                      class="size-3.5 shrink-0"
                      stroke-color="currentColor"
                    />
                  </span>
                  <span class="truncate">{{ t('views.templates.table.failed-badge') }}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent :title="t('views.templates.table.failed-message')" />
            </Tooltip>
            <span class="sr-only">{{ t('views.templates.table.failed-message') }}</span>
          </template>
        </div>
      </template>

      <template #cell-description="{ row }">
        <p class="text-xs font-medium text-gray-warm-600 line-clamp-2">
          {{ row.description }}
        </p>
      </template>

      <template #cell-owner="{ row }">
        <AvatarLabel :src="row.user.photo" :name="row.user.name" class="text-gray-warm-900" />
      </template>

      <template v-if="activeTab === 'user'" #cell-actions="{ row }">
        <div class="flex gap-4">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                icon="edit-01"
                class="aspect-square p-[10px]"
                @click="router.push({ name: 'edit-template', params: { templateId: row.id } })"
              />
            </TooltipTrigger>
            <TooltipContent :title="t('views.templates.table.actions.edit')" />
          </Tooltip>

          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                :icon="row.enabled ? 'eye' : 'eye-off'"
                class="aspect-square p-[10px]"
                @click="
                  visibilityModalData = {
                    id: row.id,
                    name: row.name,
                    action: row.enabled ? 'hide' : 'show'
                  }
                "
              />
            </TooltipTrigger>
            <TooltipContent
              :title="t(`views.templates.table.actions.${row.enabled ? 'hide' : 'show'}`)"
            />
          </Tooltip>

          <Tooltip>
            <TooltipTrigger as-child>
              <span class="inline-flex">
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
                      <DropdownMenuItem @click="openTemplateInfoModal(row.id)">
                        <Button
                          size="sm"
                          class="mr-2 w-full justify-start"
                          hierarchy="link-gray"
                          icon="info-circle"
                          icon-size="md"
                        >
                          {{ t('views.templates.table.actions.info') }}
                        </Button>
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="openAllowedModal({ id: row.id, name: row.name })">
                        <Button
                          size="sm"
                          class="mr-2 w-full justify-start"
                          hierarchy="link-gray"
                          icon="users-01"
                          icon-size="md"
                        >
                          {{ t('views.templates.table.actions.update-alloweds') }}
                        </Button>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        :disabled="isFailed(row)"
                        @click="
                          handleWithDesktopQuotaCheck(
                            () => (convertModalData = { id: row.id, name: row.name })
                          )
                        "
                      >
                        <Button
                          size="sm"
                          class="mr-2 w-full justify-start"
                          hierarchy="link-gray"
                          icon="monitor-02"
                          icon-size="md"
                        >
                          {{ t('views.templates.table.actions.template-to-desktop') }}
                        </Button>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        class="hover:bg-error-50 focus:bg-error-50"
                        @click="deleteModalData = { id: row.id, name: row.name }"
                      >
                        <Button
                          size="sm"
                          class="mr-2 w-full justify-start text-error-700"
                          hierarchy="link-gray"
                          icon="trash-04"
                          icon-size="md"
                        >
                          {{ t('views.templates.table.actions.delete') }}
                        </Button>
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              </span>
            </TooltipTrigger>
            <TooltipContent :title="t('common.actions.more')" />
          </Tooltip>
        </div>
      </template>

      <template v-else #cell-actions="{ row }">
        <div class="flex gap-2">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                icon="copy-07"
                class="aspect-square p-[10px]"
                :disabled="templateCreationCheckIsPending || isFailed(row)"
                @click="
                  handleWithTemplateQuotaCheck(() =>
                    router.push({ name: 'duplicate-template', params: { templateId: row.id } })
                  )
                "
              />
            </TooltipTrigger>
            <TooltipContent :title="t('views.templates.table.actions.duplicate')" />
          </Tooltip>
        </div>
      </template>
    </TemplateDataTable>
  </PageContainer>
</template>
