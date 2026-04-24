<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
const router = useRouter()

import {
  getRecycleBinCutoffTimeApiV4ItemRecycleBinGetUserCutoffTimeGetOptions,
  getRecycleBinItemCountUserApiV4ItemsRecycleBinGetOptions,
  emptyRecycleBinApiV4ItemRecycleBinEmptyDeleteMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import templatesEmptyImg from '@/assets/img/templates-empty.svg'
import { formatHoursToHumanReadable, formatBytes, formatRelativeTime } from '@/lib/utils'
import { computed, ref } from 'vue'

import { DataTable } from '@/components/data-table'
import { Button } from '@/components/ui/button'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { BadgeInfo } from '@/components/badge/info'
import { DropdownButton } from '@/components/dropdown-button'
import { InputField } from '@/components/input-field'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { AvatarLabel } from '@/components/avatar-label'
import { AlertModal } from '@/components/modal'
import { DeleteModal } from '@/components/recycle-bin'
import { RestoreModal } from '@/components/recycle-bin'

const { t, locale, d } = useI18n()

const {
  isPending: cutoffTimeIsPending,
  isError: cutoffTimeIsError,
  error: cutoffTimeError,
  data: cutoffTime
} = useQuery(getRecycleBinCutoffTimeApiV4ItemRecycleBinGetUserCutoffTimeGetOptions())

const showEmptyBinModal = ref(false)
const emptyBinError = ref<string | null>(null)

const { mutate: emptyBin, isPending: isEmptyingBin } = useMutation({
  ...emptyRecycleBinApiV4ItemRecycleBinEmptyDeleteMutation(),
  onSuccess: () => {
    showEmptyBinModal.value = false
    emptyBinError.value = null
  },
  onError: (err: any) => {
    emptyBinError.value = err?.description_code || 'error.generic'
  }
})

const cutoffHours = computed(() => {
  const value = (cutoffTime.value as { recycle_bin_cutoff_time?: number | null } | undefined)
    ?.recycle_bin_cutoff_time
  if (value !== undefined) return value
  return cutoffTime.value as number | null | undefined
})

const isInfiniteCutoff = computed(() => cutoffHours.value === null)

const isImmediateCutoff = computed(() => cutoffHours.value === 0)

const finiteCutoffHours = computed(() =>
  typeof cutoffHours.value === 'number' && cutoffHours.value > 0 ? cutoffHours.value : undefined
)

const {
  isPending: itemsIsPending,
  isError: itemsIsError,
  error: itemsError,
  data: items
} = useQuery(getRecycleBinItemCountUserApiV4ItemsRecycleBinGetOptions())

const searchQuery = ref('')
const showDeleteModal = ref(false)
const showRestoreModal = ref(false)
const selectedEntry = ref<any>(null)

const headers = [
  {
    name: t('views.recycle-bin.columns.name'),
    key: 'item_name',
    sortable: true
  },
  {
    name: t('views.recycle-bin.columns.size'),
    key: 'size',
    sortable: true,
    width: 'minmax(var(--spacing-24), var(--spacing-32))'
  },
  {
    name: t('views.recycle-bin.columns.content'),
    key: 'content',
    sortable: false,
    width: 'minmax(var(--spacing-40), var(--spacing-64))'
  },
  {
    name: t('views.recycle-bin.columns.deleted-at'),
    key: 'last_time_sort',
    sortable: true,
    width: 'minmax(var(--spacing-40), var(--spacing-56))'
  },
  {
    name: t('views.recycle-bin.columns.deleted-by'),
    key: 'agent_name',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-96))'
  },
  {
    name: t('views.recycle-bin.columns.actions'),
    key: 'actions',
    sortable: false,
    width: 'minmax(var(--spacing-16), var(--spacing-24))'
  }
]

const handleRestore = (row: any) => {
  selectedEntry.value = row
  showRestoreModal.value = true
}

const handleRestoreSuccess = () => {
  showRestoreModal.value = false
  selectedEntry.value = null
}

const handleDelete = (row: any) => {
  selectedEntry.value = row
  showDeleteModal.value = true
}

const handleDeleteSuccess = () => {
  showDeleteModal.value = false
  selectedEntry.value = null
}

const handleOpenEmptyBinModal = () => {
  emptyBinError.value = null
  showEmptyBinModal.value = true
}

const handleConfirmEmptyBin = () => {
  emptyBinError.value = null
  emptyBin({})
}

const handleCloseEmptyBinModal = () => {
  if (!isEmptyingBin.value) {
    showEmptyBinModal.value = false
  }
}

const getRowTimestamp = (row: any): number => row?.last?.time ?? row?.accessed ?? 0

// sortable timestamp field and filter by search query
const enrichedItems = computed(() => {
  const rawEntries = items.value?.entries
  const baseItems = (Array.isArray(rawEntries) ? rawEntries : []).map((item: any) => ({
    ...item,
    last_time_sort: getRowTimestamp(item)
  }))

  if (!searchQuery.value.trim()) return baseItems

  const query = searchQuery.value.toLowerCase()
  return baseItems.filter(
    (item: any) =>
      item.item_name?.toLowerCase().includes(query) ||
      item.agent_name?.toLowerCase().includes(query) ||
      item.item_type?.toLowerCase().includes(query)
  )
})

const getItemTypeIcon = (itemType: string): string => {
  switch (itemType) {
    case 'desktop':
      return 'monitor-02'
    case 'deployment':
      return 'layout-alt-04'
    default:
      return 'colors'
  }
}

const goToEntry = (row: any) => {
  if (!row?.id) return
  router.push({ name: 'recycle-bin-entry', params: { recycleBinId: row.id } })
}
</script>

<template>
  <main class="w-full flex justify-center">
    <div class="p-6 py-2 space-y-6 w-full max-w-480">
      <Skeleton v-if="cutoffTimeIsPending" class="h-20 w-full" />

      <Alert v-else-if="cutoffTimeIsError" variant="destructive">
        <AlertTitle>{{ t('views.recycle-bin.error.title') }}</AlertTitle>
        <AlertDescription>{{
          t(cutoffTimeError?.description_code || 'error.generic')
        }}</AlertDescription>
      </Alert>

      <Alert v-else class="border-info-300 sm:flex items-center gap-3">
        <FeaturedIconOutline
          kind="outline"
          color="brand"
          size="md"
          class="shrink-0 hidden sm:block"
        />
        <div class="flex-1 space-y-1 text-left">
          <AlertTitle>{{ t('views.recycle-bin.alert.title') }}</AlertTitle>
          <AlertDescription v-if="isImmediateCutoff">
            {{ t('views.recycle-bin.alert.immediately') }}
          </AlertDescription>
          <AlertDescription v-else-if="isInfiniteCutoff">
            {{ t('views.recycle-bin.alert.infinite') }}
          </AlertDescription>
          <AlertDescription v-else-if="finiteCutoffHours !== undefined">
            {{
              t('views.recycle-bin.alert.empty-after', {
                time: formatHoursToHumanReadable(finiteCutoffHours, locale)
              })
            }}
          </AlertDescription>
          <AlertDescription v-else>...</AlertDescription>
        </div>
        <Button hierarchy="destructive" icon="trash-01" @click="handleOpenEmptyBinModal">
          {{ t('views.recycle-bin.empty-recycle-bin') }}
        </Button>
      </Alert>

      <h2 class="text-3xl font-bold">
        {{ t('views.recycle-bin.table-title') }}
      </h2>

      <InputField
        v-model="searchQuery"
        :placeholder="t('views.recycle-bin.filters.search.placeholder')"
        icon="search-lg"
        class="w-full max-w-120"
      />

      <Alert v-if="emptyBinError" variant="destructive">
        <AlertTitle>{{ t('views.recycle-bin.error.title') }}</AlertTitle>
        <AlertDescription>{{ t(emptyBinError) }}</AlertDescription>
      </Alert>

      <div v-if="itemsIsPending" class="space-y-2">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
      </div>

      <Alert v-else-if="itemsIsError" variant="destructive">
        <AlertTitle>{{ t('views.recycle-bin.error.title') }}</AlertTitle>
        <AlertDescription>{{
          t(itemsError?.description_code || 'views.recycle-bin.error.generic')
        }}</AlertDescription>
      </Alert>

      <Empty v-if="enrichedItems.length === 0" class="md:flex-row-reverse mt-16">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none hidden md:block">
            <img :src="templatesEmptyImg" />
          </EmptyMedia>
        </EmptyHeader>

        <div class="flex flex-col items-start text-left gap-4 rounded bg-base-background/75">
          <EmptyTitle class="text-[60px] leading-[72px] font-bold text-gray-warm-950">{{
            t('views.recycle-bin.empty.title')
          }}</EmptyTitle>
          <EmptyDescription class="text-[18px]! text-gray-warm-900">{{
            t('views.recycle-bin.empty.description')
          }}</EmptyDescription>
        </div>
      </Empty>

      <DataTable
        v-else
        :headers="headers"
        :rows="enrichedItems"
        :is-clickable="true"
        row-class="hover:bg-brand-100 rounded-lg"
        @row-click="goToEntry"
      >
        <template #cell-item_name="{ row }">
          <div class="flex items-center gap-2 my-4">
            <Icon :name="getItemTypeIcon(row.item_type)" size="md" />
            <span class="font-semibold">{{ row.item_name }}</span>
          </div>
        </template>
        <template #cell-size="{ row }">
          {{ formatBytes(row.size) }}
        </template>
        <template #cell-last_time_sort="{ row }">
          <span
            v-if="getRowTimestamp(row)"
            :title="formatRelativeTime(getRowTimestamp(row), locale)"
          >
            {{ d(getRowTimestamp(row) * 1000, { dateStyle: 'short', timeStyle: 'medium' }) }}
          </span>
          <span v-else>—</span>
        </template>
        <template #cell-content="{ row }">
          <div class="flex gap-2">
            <BadgeInfo
              v-if="row.desktops"
              :icon="getItemTypeIcon('desktop')"
              :content="row.desktops"
            />
            <BadgeInfo
              v-if="row.templates"
              :icon="getItemTypeIcon('template')"
              :content="row.templates"
            />
            <BadgeInfo
              v-if="row.deployments"
              :icon="getItemTypeIcon('deployment')"
              :content="row.deployments"
            />
          </div>
        </template>
        <template #cell-agent_name="{ row }">
          <AvatarLabel
            :src="row.agent_photo"
            :name="row.agent_name"
            size="sm"
            class="text-gray-warm-900"
          />
        </template>
        <template #cell-actions="{ row }">
          <span @click.stop @keydown.enter.stop @keydown.space.stop>
            <DropdownButton
              :menu-content="[
                {
                  icon: 'refresh-ccw-05',
                  text: t('views.recycle-bin.actions.restore'),
                  onClick: () => handleRestore(row)
                },
                {
                  icon: 'trash-03',
                  text: t('views.recycle-bin.actions.delete-permanently'),
                  onClick: () => handleDelete(row),
                  class: 'text-error-700'
                }
              ]"
            />
          </span>
        </template>
      </DataTable>

      <DeleteModal
        v-model:open="showDeleteModal"
        :recycle-bin-id="selectedEntry?.id || ''"
        :item-name="selectedEntry?.item_name"
        :on-success="handleDeleteSuccess"
      />
    </div>
  </main>

  <!-- Restore Modal -->
  <RestoreModal
    v-model:open="showRestoreModal"
    :recycle-bin-id="selectedEntry?.id || ''"
    :item-name="selectedEntry?.item_name"
    :on-success="handleRestoreSuccess"
  />
  <AlertModal
    :open="showEmptyBinModal"
    level="danger"
    size="md"
    :title="t('components.recycle-bin.empty-modal.title')"
    :loading="isEmptyingBin"
    @close="handleCloseEmptyBinModal"
  >
    <template #description>
      <div v-if="emptyBinError" class="mb-4">
        <Alert variant="destructive">
          <AlertTitle>{{ t('views.recycle-bin.empty-modal.error') }}</AlertTitle>
          <AlertDescription>{{ t(emptyBinError) }}</AlertDescription>
        </Alert>
      </div>
      <p>{{ t('components.recycle-bin.empty-modal.description') }}</p>
    </template>

    <template #footer>
      <Button
        hierarchy="secondary-gray"
        :disabled="isEmptyingBin"
        class="w-2/7"
        @click="handleCloseEmptyBinModal"
      >
        {{ t('components.recycle-bin.empty-modal.cancel') }}
      </Button>
      <Button
        hierarchy="destructive"
        :icon="isEmptyingBin ? 'loading-02' : undefined"
        :icon-class="{ 'motion-safe:animate-[spin_2s_linear_infinite]': isEmptyingBin }"
        :loading="isEmptyingBin"
        :disabled="isEmptyingBin"
        class="w-3/7"
        @click="handleConfirmEmptyBin"
      >
        {{ t('components.recycle-bin.empty-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
