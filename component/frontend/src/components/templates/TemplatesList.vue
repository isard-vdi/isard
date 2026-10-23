<script setup lang="ts">
import { TemplateDataTable } from '@/components/data-table'
import { Icon } from '@/components/icon'
import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import Progress from '@/components/ui/progress/Progress.vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  getUserTemplatesOptions,
  getUserSharedTemplatesOptions,
  getUserOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { TemplateStatusEnum, type UserSharedTemplate, type UserTemplate } from '@/gen/oas/apiv4'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toggleVariants } from '@/components/ui/toggle'
import { computed, watch } from 'vue'
import { useOwnershipTab, type OwnershipTab } from '@/composables/useOwnershipTab'
import { TruncatedText } from '@/components/truncated-text'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  TemplateStatusBadge,
  TemplateStatusImage,
  isTemplateFailed,
  templateRowCellClass,
  templateStatus
} from '@/components/template-status'

const { t } = useI18n()

interface Props {
  selectable?: boolean
  pageSize?: number
  paginationPageSizes?: number[]
  selectedId?: string
  inlineTabs?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  rowClick: [any] // TODO: type this
  showInfoModal: [string]
}>()

const tabModel = defineModel<OwnershipTab | undefined>('activeTemplateTab')

const queryClient = useQueryClient()

const {
  data: user,
  isPending: userIsPending,
  isError: userIsError,
  error: userError
} = useQuery({ ...getUserOptions(), staleTime: Infinity })

// A failed template is listed but cannot be picked, so a tab holding nothing else
// is an empty tab as far as this list is concerned.
const isSelectable = (template: UserTemplate | UserSharedTemplate) =>
  template.status !== TemplateStatusEnum.FAILED

const { activeTab: localActiveTab, isResolving: tabIsResolving } = useOwnershipTab({
  hasOwned: async () => {
    const me = await queryClient.fetchQuery({ ...getUserOptions(), staleTime: Infinity })
    if (me.role === 'user') return false
    const { templates } = await queryClient.fetchQuery(getUserTemplatesOptions())
    return templates.some(isSelectable)
  },
  hasShared: async () =>
    (await queryClient.fetchQuery(getUserSharedTemplatesOptions())).templates.some(isSelectable),
  fallback: () => (user.value?.role === 'user' ? 'shared' : 'user'),
  pinned: tabModel.value,
  // Not a page: the tab belongs to the flow, not to the URL.
  param: false
})

watch(localActiveTab, (tab) => {
  if (tab !== undefined) tabModel.value = tab
})

const {
  isPending: userTemplatesIsPending,
  isError: userTemplatesIsError,
  error: userTemplatesError,
  data: userTemplates,
  isEnabled: userTemplatesIsEnabled
} = useQuery({
  ...getUserTemplatesOptions(),
  enabled: computed(() => user?.value?.role !== 'user' && localActiveTab.value === 'user')
})

const myTemplates = computed(() => {
  return userTemplates?.value?.templates || []
})

const userTemplatesHeader = computed(() => [
  { name: '', key: 'image', width: 'var(--spacing-48)' },
  {
    name: t('views.templates.table.headers.name'),
    key: 'name',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-80))'
  },
  {
    name: t('views.templates.table.headers.description'),
    key: 'description',
    sortable: true,
    width: 'minmax(var(--spacing-56), 1fr)'
  },
  { name: '', key: 'actions', width: 'max-content' }
])

// The owner column sorts on the row value, so flatten the user object into a string.
const withOwnerName = (template: UserSharedTemplate) => ({
  ...template,
  owner: typeof template.user === 'string' ? template.user : (template.user?.name ?? '')
})

const userSharedTemplates = computed(() => {
  return (sharedTemplates?.value?.templates || []).map(withOwnerName)
})

const userSharedTemplatesHeader = computed(() => [
  { name: '', key: 'image', width: 'var(--spacing-48)' },
  {
    name: t('views.templates.table.headers.name'),
    key: 'name',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-80))'
  },
  {
    name: t('views.templates.table.headers.description'),
    key: 'description',
    sortable: true,
    width: 'minmax(var(--spacing-56), 1fr)'
  },
  {
    name: t('views.templates.table.headers.owner'),
    key: 'owner',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-64))'
  },
  {
    name: t('views.templates.table.headers.category'),
    key: 'category_name',
    sortable: true,
    width: 'minmax(max-content, var(--spacing-40))'
  },
  {
    name: t('views.templates.table.headers.group'),
    key: 'group_name',
    sortable: true,
    width: 'minmax(max-content, var(--spacing-40))'
  },
  { name: '', key: 'actions', width: 'max-content' }
])

const {
  isPending: sharedTemplatesIsPending,
  isError: sharedTemplatesIsError,
  error: sharedTemplatesError,
  data: sharedTemplates,
  isEnabled: sharedTemplatesIsEnabled
} = useQuery({
  ...getUserSharedTemplatesOptions(),
  enabled: computed(() => localActiveTab.value === 'shared')
})

const tableIsLoading = computed(() => {
  return (
    tabIsResolving.value ||
    (userTemplatesIsEnabled.value && userTemplatesIsPending.value) ||
    (sharedTemplatesIsEnabled.value && sharedTemplatesIsPending.value) ||
    userIsPending.value
  )
})

const tableIsError = computed(() => {
  return userTemplatesIsError.value || sharedTemplatesIsError.value || userIsError.value
})

const isFailed = isTemplateFailed
const rowStatus = (row: Record<string, unknown>) =>
  templateStatus(row, localActiveTab.value === 'user')
const rowCellClass = (row: Record<string, unknown>) => templateRowCellClass(rowStatus(row))

function templateProgressPercent(progress: unknown): number {
  return (progress as { total_percent?: number } | undefined)?.total_percent ?? 0
}
</script>
<template>
  <main class="flex flex-col gap-6 w-full">
    <div
      v-if="tableIsLoading"
      class="text-center text-gray-warm-500 flex justify-center items-center"
    >
      <Icon name="loading-03" size="sm" class="animate-spin mr-2" />
      {{ t('api.loading') }}
    </div>
    <div v-else-if="tableIsError" class="text-center text-error-500">
      {{ t('api.loading-error') }}
    </div>
    <TemplateDataTable
      :headers="localActiveTab === 'user' ? userTemplatesHeader : userSharedTemplatesHeader"
      :rows="localActiveTab === 'user' ? myTemplates : userSharedTemplates"
      :loading="tableIsLoading"
      :page-size="props.pageSize"
      :pagination-page-sizes="props.paginationPageSizes"
      :inline-tabs="props.inlineTabs"
      :is-clickable="true"
      :is-row-disabled="isFailed"
      :row-cell-class="rowCellClass"
      autofocus-search
      :disabled-tooltip="t('views.templates.table.failed-message')"
      @row-click="selectable && !isFailed($event) ? emit('rowClick', $event) : null"
      :selected-id="props.selectedId"
    >
      <template #tabs>
        <Tabs v-model="localActiveTab">
          <TabsList class="flex w-fit gap-[--spacing(1)] rounded-md">
            <TabsTrigger
              v-if="user?.role !== 'user'"
              value="user"
              :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
            >
              <Icon name="user-03" stroke-color="currentColor" />
              {{ t('components.templates.template-type.owned') }}
            </TabsTrigger>
            <TabsTrigger
              value="shared"
              :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
            >
              <Icon name="share-06" stroke-color="currentColor" />
              {{ t('components.templates.template-type.shared') }}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </template>

      <template #cell-image="{ row }">
        <TemplateStatusImage
          :image-url="row.image.url"
          :status="rowStatus(row)"
          :tooltip="!isFailed(row)"
        />
      </template>

      <template #cell-name="{ row }">
        <div class="flex flex-col">
          <TruncatedText :title="row.name" class="text-sm font-semibold text-gray-warm-900" />
          <TemplateStatusBadge
            v-if="rowStatus(row)"
            :status="rowStatus(row)!"
            :tooltip="!isFailed(row)"
          />
        </div>
      </template>

      <template #cell-description="{ row }">
        <div v-if="row.status === 'CreatingTemplate'">
          <div class="text-end text-xs mb-0.5">{{ templateProgressPercent(row.progress) }}%</div>
          <Progress
            :class="'h-2 text-info-400 w-50'"
            :model-value="templateProgressPercent(row.progress)"
          />
        </div>
        <p v-else class="text-xs font-medium text-gray-warm-600 line-clamp-2">
          {{ row.description }}
        </p>
      </template>

      <template #cell-owner="{ row }">
        <AvatarLabel :src="row.user.photo" :name="row.user.name" class="text-gray-warm-900" />
      </template>

      <template #cell-category_name="{ row }">
        <p class="text-sm text-gray-warm-900 truncate">{{ row.category_name }}</p>
      </template>

      <template #cell-group_name="{ row }">
        <p class="text-sm text-gray-warm-900 truncate">{{ row.group_name }}</p>
      </template>

      <template #cell-actions="{ row }">
        <div class="flex gap-2">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                icon="info-circle"
                class="aspect-square p-[10px]"
                @click.stop="emit('showInfoModal', row.id)"
                @keydown.enter.stop
                @keydown.space.stop
              />
            </TooltipTrigger>
            <TooltipContent :title="t('views.templates.table.actions.info')" />
          </Tooltip>
        </div>
      </template>
    </TemplateDataTable>
  </main>
</template>
