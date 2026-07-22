<script setup lang="ts">
import { TemplateDataTable } from '@/components/data-table'
import { Icon } from '@/components/icon'
import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import Progress from '@/components/ui/progress/Progress.vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import {
  getUserTemplatesOptions,
  //   // getUserSharedTemplates
  getUserOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getUserSharedTemplates } from '@/gen/oas/apiv4/'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toggleVariants } from '@/components/ui/toggle'
import { computed, watch } from 'vue'
import { ref } from 'vue'

const { t } = useI18n()

interface Props {
  activeTemplateTab: 'user' | 'shared'
  selectable?: boolean
  pageSize?: number
  paginationPageSizes?: number[]
  selectedId?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  rowClick: [any] // TODO: type this
  'update:activeTemplateTab': []
  showInfoModal: [string]
}>()

const localActiveTab = ref(props.activeTemplateTab)

const {
  data: user,
  isPending: userIsPending,
  isError: userIsError,
  error: userError
} = useQuery({ ...getUserOptions(), staleTime: Infinity })

const {
  isPending: userTemplatesIsPending,
  isError: userTemplatesIsError,
  error: userTemplatesError,
  data: userTemplates,
  isEnabled: userTemplatesIsEnabled
} = useQuery({
  ...getUserTemplatesOptions(),
  enabled: computed(() => user?.value?.role !== 'user')
})

const myTemplates = computed(() => {
  return userTemplates?.value?.templates || []
})

const userTemplatesHeader = [
  { name: '', key: 'image', width: 'var(--spacing-48)' },
  { name: 'Name', key: 'name', width: 'minmax(var(--spacing-48), var(--spacing-80))' },
  { name: 'Description', key: 'description', width: 'minmax(var(--spacing-56), 1fr)' },
  { name: '', key: 'actions', width: 'max-content' }
]

const userSharedTemplates = computed(() => {
  return sharedTemplates?.value?.templates || []
})

const userSharedTemplatesHeader = [
  { name: '', key: 'image', width: 'var(--spacing-48)' },
  { name: 'Name', key: 'name', width: 'minmax(var(--spacing-48), var(--spacing-80))' },
  { name: 'Description', key: 'description', width: 'minmax(var(--spacing-56), 1fr)' },
  { name: 'Owner', key: 'owner', width: 'minmax(var(--spacing-48), var(--spacing-64))' },
  { name: '', key: 'actions', width: 'max-content' }
]

const {
  mutate: fetchSharedTemplates,
  isPending: fetchSharedTemplatesIsPending,
  isError: fetchSharedTemplatesIsError,
  error: fetchSharedTemplatesError,
  data: sharedTemplates
} = useMutation({
  mutationFn: async () => {
    const { data } = await getUserSharedTemplates({
      throwOnError: true
    })
    return data
  }
})

const clickSharedTemplates = async () => {
  if (sharedTemplates?.value) return
  fetchSharedTemplates()
}

watch(
  () => user?.value,
  (newUser) => {
    if (newUser?.role === 'user') {
      localActiveTab.value = 'shared'
      fetchSharedTemplates()
    }
  },
  { immediate: true }
)

const tableIsLoading = computed(() => {
  return (
    (userTemplatesIsEnabled.value && userTemplatesIsPending.value) ||
    fetchSharedTemplatesIsPending.value ||
    userIsPending.value
  )
})

const tableIsError = computed(() => {
  return userTemplatesIsError.value || fetchSharedTemplatesIsError.value || userIsError.value
})

const isFailed = (row: Record<string, unknown>) => row.status === 'Failed'
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
      {{ t('api.error') }}
    </div>
    <TemplateDataTable
      :headers="localActiveTab === 'user' ? userTemplatesHeader : userSharedTemplatesHeader"
      :rows="localActiveTab === 'user' ? myTemplates : userSharedTemplates"
      :loading="tableIsLoading"
      :page-size="props.pageSize"
      :pagination-page-sizes="props.paginationPageSizes"
      :is-clickable="true"
      :is-row-disabled="isFailed"
      :disabled-tooltip="t('views.templates.table.failed-message')"
      @row-click="selectable && !isFailed($event) ? emit('rowClick', $event) : null"
      :selected-id="props.selectedId"
    >
      <template #filters-left>
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
              @click="clickSharedTemplates"
            >
              <Icon name="share-06" stroke-color="currentColor" />
              {{ t('components.templates.template-type.shared') }}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </template>

      <template #cell-image="{ row }">
        <div class="relative">
          <div
            class="w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover"
            :class="{ 'opacity-40 grayscale': isFailed(row) }"
            :style="{
              backgroundImage: `url(${row.image.url})`
            }"
          ></div>
          <div
            v-if="isFailed(row)"
            aria-hidden="true"
            class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center bg-error-200/60 p-1.5 rounded-full backdrop-blur-xs border-2 border-base-white ring-[3px] ring-error-600/20 ring-offset-1 ring-offset-base-white/30 shadow-md shadow-error-700"
          >
            <Icon name="alert-triangle" size="xl" stroke-color="error-700" />
          </div>
        </div>
      </template>

      <template #cell-name="{ row }">
        <div class="flex flex-col">
          <p class="text-sm font-semibold text-gray-warm-900 truncate">
            {{ row.name }}
          </p>
          <div
            v-if="isFailed(row)"
            class="inline-flex items-center gap-1.5 font-semibold max-w-full w-max text-xs text-error-600"
          >
            <span aria-hidden="true" class="contents">
              <Icon name="info-circle" class="size-3.5 shrink-0" stroke-color="currentColor" />
            </span>
            <span class="truncate">{{ t('views.templates.table.failed-badge') }}</span>
          </div>
        </div>
      </template>

      <template #cell-description="{ row }">
        <div v-if="row.status === 'CreatingTemplate'">
          <div class="text-end text-xs mb-0.5">
            {{ (row.progress as { total_percent?: number } | undefined)?.total_percent ?? 0 }}%
          </div>
          <Progress
            :class="'h-2 text-info-400 w-50'"
            :model-value="
              (row.progress as { total_percent?: number } | undefined)?.total_percent ?? 0
            "
          />
        </div>
        <p v-else class="text-xs font-medium text-gray-warm-600 line-clamp-2">
          {{ row.description }}
        </p>
      </template>

      <template #cell-owner="{ row }">
        <AvatarLabel :src="row.user.photo" :name="row.user.name" class="text-gray-warm-900" />
      </template>

      <template #cell-actions="{ row }">
        <div class="flex gap-2">
          <Button
            hierarchy="secondary-gray"
            icon="info-circle"
            class="aspect-square p-[10px]"
            @click.stop="emit('showInfoModal', row.id)"
            @keydown.enter.stop
            @keydown.space.stop
          />
        </div>
      </template>
    </TemplateDataTable>
  </main>
</template>
