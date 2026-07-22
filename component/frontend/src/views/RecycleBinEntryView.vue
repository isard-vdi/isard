<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { DataTable } from '@/components/data-table'
import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import { formatRelativeTime, formatBytes } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toggleVariants } from '@/components/ui/toggle'
import { InputField } from '@/components/input-field'
import { Badge } from '@/components/badge'
import { Icon, CopyIcon } from '@/components/icon'
import { TooltipTrigger, TooltipContent, Tooltip } from '@/components/ui/tooltip'
import { Label } from '@/components/ui/label'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { DeleteModal } from '@/components/recycle-bin'
import { getRecycleBinOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import templatesEmptyImg from '@/assets/img/templates-empty.svg'
import bannerImg from '@/assets/img/rcb-entry-banner.svg'
import { RestoreModal } from '@/components/recycle-bin'

const { t, locale, d } = useI18n()
const route = useRoute()

const router = useRouter()

const recycleBinId = computed(() => {
  const param = route.params.recycleBinId || route.params.id
  if (Array.isArray(param)) return param[0] ?? ''
  return typeof param === 'string' ? param : ''
})

const {
  isPending: entryIsPending,
  isError: entryIsError,
  error: entryError,
  data: entry
} = useQuery({
  ...getRecycleBinOptions({
    path: { recycle_bin_id: recycleBinId.value }
  }),
  enabled: computed(() => Boolean(recycleBinId.value))
})

const showRestoreModal = ref(false)
const showDeleteModal = ref(false)

const handleRestore = () => {
  showRestoreModal.value = true
}

const handleRestoreSuccess = () => {
  showRestoreModal.value = false
  router.push({ name: 'recycle-bin' })
}

const handleDelete = () => {
  showDeleteModal.value = true
}

const handleDeleteSuccess = () => {
  showDeleteModal.value = false
  router.push({ name: 'recycle-bin' })
}

function getItemTypeIcon(itemType: string) {
  switch (itemType) {
    case 'desktop':
    case 'desktops':
      return 'monitor-02'
    case 'deployment':
    case 'deployments':
      return 'layout-alt-04'
    case 'template':
    case 'templates':
      return 'colors'
    case 'storage':
    case 'storages':
      return 'save-02'
    default:
      return 'colors'
  }
}

function goToRecycleBinEntry(row: any) {
  if (row.id) {
    router.push({ name: 'recycle-bin-entry', params: { recycleBinId: row.id } })
  }
}

const searchQuery = ref('')
const selectedTab = ref<string | null>(null)

const availableTabs = computed(() => {
  const current = entry.value
  if (!current) return []
  return [
    {
      key: 'desktops',
      label: t('views.recycle-bin.entry.tabs.desktops'),
      items: current.desktops ?? []
    },
    {
      key: 'deployments',
      label: t('views.recycle-bin.entry.tabs.deployments'),
      items: current.deployments ?? []
    },
    {
      key: 'templates',
      label: t('views.recycle-bin.entry.tabs.templates'),
      items: current.templates ?? []
    },
    {
      key: 'storages',
      label: t('views.recycle-bin.entry.tabs.storages'),
      items: current.storages ?? []
    }
  ].filter((tab) => Array.isArray(tab.items) && tab.items.length > 0)
})

watch(
  [availableTabs, entry],
  ([tabs, entryVal]) => {
    if (!tabs.length) {
      selectedTab.value = null
      return
    }

    // Set default tab based on entry type
    const entryType = entryVal?.item_type
    let defaultTab = tabs[0].key
    if (entryType === 'template' && tabs.some((tab) => tab.key === 'templates')) {
      defaultTab = 'templates'
    } else if (entryType === 'desktop' && tabs.some((tab) => tab.key === 'desktops')) {
      defaultTab = 'desktops'
    } else if (entryType === 'deployment' && tabs.some((tab) => tab.key === 'deployments')) {
      defaultTab = 'deployments'
    } else if (entryType === 'storage' && tabs.some((tab) => tab.key === 'storages')) {
      defaultTab = 'storages'
    }

    if (!selectedTab.value || !tabs.some((tab) => tab.key === selectedTab.value)) {
      selectedTab.value = defaultTab
    }
  },
  { immediate: true }
)

const desktopRows = computed(() =>
  (entry.value?.desktops ?? []).map((item: any) => ({
    id: item.id,
    name: item.name,
    owner: item.username,
    category: item.category.name,
    group: item.group.name,
    accessed: item.accessed
  }))
)

const templateRows = computed(() =>
  (entry.value?.templates ?? []).map((item: any) => ({
    id: item.id,
    name: item.name,
    owner: item.username,
    category: item.category.name,
    group: item.group.name,
    accessed: item.accessed
  }))
)

const deploymentRows = computed(() =>
  (entry.value?.deployments ?? []).map((item: any) => ({
    id: item.id,
    name: item.name,
    desktop: item.create_dict[0].name,
    user: item.user,
    category: item.category.name,
    group: item.group.name
  }))
)

const storageRows = computed(() =>
  (entry.value?.storages ?? []).map((item: any) => {
    const domains = Array.isArray(item.domains)
      ? item.domains.map((domain: any) => domain?.name ?? domain?.id ?? domain).join(', ')
      : ''
    return {
      id: item.id,
      path: item.directory_path,
      status: item.status,
      format: item.type,
      size: item['qemu-img-info']?.['virtual-size'] ?? '-',
      used: item['qemu-img-info']?.['actual-size'] ?? '-',
      parent: item.parent,
      owner: item.user,
      domains
    }
  })
)

const activeRows = computed(() => {
  switch (selectedTab.value) {
    case 'desktops':
      return desktopRows.value
    case 'deployments':
      return deploymentRows.value
    case 'templates':
      return templateRows.value
    case 'storages':
      return storageRows.value
    default:
      return []
  }
})

const filteredRows = computed(() => {
  if (!searchQuery.value.trim()) return activeRows.value
  const query = searchQuery.value.toLowerCase()
  return activeRows.value.filter((row: Record<string, any>) =>
    Object.values(row).some((value) =>
      String(value ?? '')
        .toLowerCase()
        .includes(query)
    )
  )
})

const domainHeaders = computed(() => [
  {
    name: t('views.recycle-bin.entry.tables.common.name'),
    key: 'name',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.common.owner'),
    key: 'owner',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.common.category'),
    key: 'category',
    sortable: true,
    width: 'minmax(var(--spacing-10), var(--spacing-40))'
  },
  {
    name: t('views.recycle-bin.entry.tables.common.group'),
    key: 'group',
    sortable: true,
    width: 'minmax(var(--spacing-10), var(--spacing-40))'
  },
  {
    name: t('views.recycle-bin.entry.tables.common.accessed'),
    key: 'accessed',
    sortable: true,
    width: 'minmax(var(--spacing-8), var(--spacing-56))'
  }
])

const deploymentHeaders = computed(() => [
  {
    name: t('views.recycle-bin.entry.tables.common.name'),
    key: 'name',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.common.owner'),
    key: 'user',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-80))'
  },
  {
    name: t('views.recycle-bin.entry.tables.common.category'),
    key: 'category',
    sortable: true,
    width: 'minmax(var(--spacing-24), var(--spacing-40))'
  },
  {
    name: t('views.recycle-bin.entry.tables.common.group'),
    key: 'group',
    sortable: true,
    width: 'minmax(var(--spacing-24), var(--spacing-40))'
  }
])

const storageHeaders = computed(() => [
  {
    name: t('views.recycle-bin.entry.tables.storages.id'),
    key: 'id',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.format'),
    key: 'format',
    sortable: true,
    width: 'minmax(var(--spacing-8), var(--spacing-24))'
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.size'),
    key: 'size',
    sortable: true,

    width: 'minmax(var(--spacing-8), var(--spacing-24))'
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.used'),
    key: 'used',
    sortable: true,

    width: 'minmax(var(--spacing-8), var(--spacing-24))'
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.parent'),
    key: 'parent',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.owner'),
    key: 'owner',
    sortable: true
  },
  {
    name: t('views.recycle-bin.entry.tables.storages.domains'),
    key: 'domains',
    sortable: false
  }
])

const activeHeaders = computed(() => {
  switch (selectedTab.value) {
    case 'desktops':
    case 'templates':
      return domainHeaders.value
    case 'deployments':
      return deploymentHeaders.value
    case 'storages':
      return storageHeaders.value
    default:
      return []
  }
})

const deletedAtLabel = computed(() => {
  if (!entry.value?.accessed) return t('views.recycle-bin.entry.banner.unknown-date')
  return new Date(entry.value.accessed * 1000).toLocaleString(locale.value)
})

const deletedAtRelative = computed(() =>
  entry.value?.accessed ? formatRelativeTime(entry.value.accessed, locale.value) : '...'
)

const totalSizeLabel = computed(() => {
  if (entry.value?.size === null || entry.value?.size === undefined) {
    return t('views.recycle-bin.entry.banner.unknown-size')
  }
  return formatBytes(entry.value.size)
})

const entryErrorKey = computed(
  () => (entryError as { description_code?: string })?.description_code
)
</script>

<template>
  <main class="w-full flex justify-center">
    <div class="p-6 py-2 space-y-6 w-full max-w-480">
      <div class="flex items-center gap-3">
        <Button
          icon="arrow-left"
          hierarchy="link-color"
          class="text-lg w-min"
          :as="RouterLink"
          :to="{ name: 'recycle-bin' }"
        >
          {{ t('layouts.single-page.go-back') }}
        </Button>
        <div class="ml-auto flex flex-wrap gap-2">
          <Button
            :icon="'refresh-cw-01'"
            hierarchy="secondary-gray"
            :disabled="!entry"
            @click="handleRestore"
          >
            {{ t('views.recycle-bin.actions.restore') }}
          </Button>
          <Button hierarchy="destructive" icon="trash-04" :disabled="!entry" @click="handleDelete">
          </Button>
        </div>
      </div>

      <div v-if="entryIsPending" class="space-y-4">
        <Skeleton class="h-40 w-full" />
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
      </div>

      <Alert v-else-if="entryIsError" variant="destructive">
        <AlertTitle>{{ t('views.recycle-bin.error.title') }}</AlertTitle>
        <AlertDescription>{{
          t(entryErrorKey || 'views.recycle-bin.error.generic')
        }}</AlertDescription>
      </Alert>

      <template v-else>
        <!-- Banner -->
        <div
          class="bg-warning-50 rounded-lg border border-gray-warm-300 flex flex-row overflow-hidden gap-8 px-2 pt-4"
        >
          <img
            :src="bannerImg"
            :alt="t('views.recycle-bin.entry.banner.alt')"
            class="max-h-32 mb-0 hidden sm:block"
          />

          <div class="space-y-2 grid">
            <h2 class="text-lg font-semibold text-warning-900 flex items-center gap-2">
              <Icon :name="getItemTypeIcon(entry?.item_type || '')" size="md" />
              {{ entry?.item_name }}
            </h2>
          </div>

          <div class="grid sm:grid-cols-2 gap-16 items-center">
            <div class="flex flex-col gap-1 justify-center">
              <Label>{{ t('views.recycle-bin.entry.banner.deleted-on') }}</Label>
              <Tooltip>
                <TooltipTrigger>
                  <p>{{ deletedAtLabel }}</p>
                </TooltipTrigger>
                <TooltipContent :title="deletedAtRelative" />
              </Tooltip>
            </div>
            <div class="flex flex-col gap-1 justify-center">
              <Label>{{ t('views.recycle-bin.entry.banner.total-size') }}</Label>
              <p>{{ totalSizeLabel }}</p>
            </div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex flex-col gap-4 md:flex-row md:items-start">
          <Tabs v-model="selectedTab">
            <TabsList class="flex w-fit gap-[--spacing(1)] rounded-md flex-wrap">
              <TabsTrigger
                v-for="tab in availableTabs"
                :key="tab.key"
                :value="tab.key"
                :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
              >
                <Icon :name="getItemTypeIcon(tab.key)" stroke-color="currentColor" />
                {{ t(`views.recycle-bin.entry.tabs.${tab.key}`, { count: tab.items.length }) }}
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <InputField
            v-model="searchQuery"
            :placeholder="t('views.recycle-bin.entry.filters.search.placeholder')"
            icon="search-lg"
            class="w-full max-w-120 md:ml-auto"
          />
        </div>

        <!-- Empty component -->
        <Empty v-if="filteredRows.length === 0" class="md:flex-row-reverse">
          <EmptyHeader>
            <EmptyMedia variant="default" class="select-none pointer-events-none hidden md:block">
              <img :src="templatesEmptyImg" />
            </EmptyMedia>
          </EmptyHeader>
          <div class="flex flex-col items-start text-left rounded bg-base-background/75">
            <EmptyTitle class="text-[30px] leading-16 font-bold text-gray-warm-950">{{
              t('views.recycle-bin.entry.empty.title')
            }}</EmptyTitle>
            <EmptyDescription class="text-4! text-gray-warm-900">{{
              t('views.recycle-bin.entry.empty.description')
            }}</EmptyDescription>
          </div>
        </Empty>

        <!-- Table -->
        <DataTable
          v-else
          :headers="activeHeaders"
          :rows="filteredRows"
          :is-clickable="true"
          :cell-class="''"
        >
          <template #cell-name="{ row }">
            <p class="text-sm font-semibold text-gray-warm-900 truncate">
              {{ row.name }}
            </p>
          </template>
          <template #cell-owner="{ row }">
            <AvatarLabel
              :src="row.owner_photo"
              :name="row.owner || '—'"
              size="sm"
              class="text-gray-warm-900"
            />
          </template>
          <template #cell-user="{ row }">
            <AvatarLabel
              :src="row.user_photo"
              :name="row.user || '—'"
              size="sm"
              class="text-gray-warm-900"
            />
          </template>
          <template #cell-id="{ row }">
            <span class="flex flex-row items-center gap-2 py-3">
              <CopyIcon v-if="row.id" :value="row.id" />
              <span v-if="row.id" class="inline-flex items-center">
                {{ row.id }}
              </span>
              <span v-else>—</span>
            </span>
          </template>
          <template #cell-category="{ row }">
            <Badge
              v-if="row.category"
              color="violet"
              size="sm"
              :content="row.category"
              class="my-2"
              shape="square"
            />
            <span v-else>—</span>
          </template>
          <template #cell-parent="{ row }">
            <span class="flex flex-row items-center gap-2 py-3">
              <CopyIcon v-if="row.parent" :value="row.parent" />
              <span v-if="row.parent" class="inline-flex items-center">
                {{ row.parent }}
              </span>
              <span v-else>—</span>
            </span>
          </template>
          <template #cell-group="{ row }">
            <Badge
              v-if="row.group"
              color="indigo"
              size="sm"
              shape="square"
              :content="row.group"
              class="my-2"
            />
            <span v-else>—</span>
          </template>
          <template #cell-accessed="{ row }">
            <span v-if="row.accessed" :title="formatRelativeTime(row.accessed, locale)">
              {{ d(row.accessed * 1000, { dateStyle: 'short', timeStyle: 'medium' }) }}
            </span>
            <span v-else>—</span>
          </template>
          <template #cell-size="{ row }">
            <span v-if="typeof row.size === 'number'">{{ formatBytes(row.size) }}</span>
            <span v-else>—</span>
          </template>
          <template #cell-used="{ row }">
            <span v-if="typeof row.used === 'number'">{{ formatBytes(row.used) }}</span>
            <span v-else>—</span>
          </template>
        </DataTable>
        <DeleteModal
          v-model:open="showDeleteModal"
          :recycle-bin-id="recycleBinId"
          :item-name="entry?.item_name"
          :on-success="handleDeleteSuccess"
        />
      </template>
    </div>
  </main>

  <!-- Restore Modal -->
  <RestoreModal
    v-model:open="showRestoreModal"
    :recycle-bin-id="recycleBinId"
    :item-name="entry?.item_name"
    :on-success="handleRestoreSuccess"
  />
</template>
