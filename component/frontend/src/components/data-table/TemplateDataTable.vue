<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  useVueTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnFiltersState,
  type SortingFn,
  type SortingState,
  getFilteredRowModel
} from '@tanstack/vue-table'

import { valueUpdater } from '@/lib/utils'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import DatatablePagination from '@/components/ui/data-table-pagination/DatatablePagination.vue'
import { DataTableHead } from '@/components/ui/data-table'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import { EmptyState, PageToolbar, SearchInput, type EmptyStateKind } from '@/components/page'

const { t, locale } = useI18n()

export interface HeaderCell {
  name: string
  key: string

  sortable?: boolean

  width?: string
}

interface Props {
  headers: HeaderCell[]
  rows: Record<string, unknown>[]
  pageSize?: number
  paginationPageSizes?: number[]
  loading?: boolean
  isClickable: boolean
  isRowDisabled?: (row: Record<string, unknown>) => boolean
  disabledTooltip?: string
  selectedId?: string
  defaultSort?: { key: string; desc?: boolean }
  hideToolbar?: boolean
  inlineTabs?: boolean
  emptyKind?: EmptyStateKind
  // Row count before any filtering, so a first run can be told from a fruitless search.
  totalRows?: number
  autofocusSearch?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10,
  paginationPageSizes: undefined,
  loading: false,
  isClickable: false,
  defaultSort: undefined,
  hideToolbar: false,
  inlineTabs: false,
  emptyKind: 'templates',
  totalRows: undefined,
  autofocusSearch: false
})

// Owned here by default, but a view laying out its own toolbar can drive it.
const search = defineModel<string>('search', { default: '' })

const emit = defineEmits<{
  rowClick: [Record<string, unknown>]
}>()

const pageSize = computed(() => props.pageSize ?? 10)
const columnFilters = ref<ColumnFiltersState>([])

// Left to itself tanstack picks a comparator by peeking at the rows past the
// tenth, so the same table sorts case-sensitively with ten templates and
// case-insensitively with eleven. Pin one, and let it order the way the
// reader's language does: accents in place, "Template 2" before "Template 10".
const collator = computed(() => new Intl.Collator(locale.value, { numeric: true }))

const compareRows: SortingFn<Record<string, unknown>> = (rowA, rowB, columnId) => {
  const a = rowA.getValue(columnId)
  const b = rowB.getValue(columnId)

  if (typeof a === 'number' && typeof b === 'number') return a - b

  // A missing value reads as an empty one, and sorts with them.
  return collator.value.compare(a == null ? '' : String(a), b == null ? '' : String(b))
}

const sorting = ref<SortingState>(
  props.defaultSort ? [{ id: props.defaultSort.key, desc: props.defaultSort.desc ?? false }] : []
)

const table = useVueTable({
  get data() {
    return props.rows
  },
  get columns() {
    return props.headers.map((header) => ({
      accessorKey: header.key,
      header: header.name,
      sortingFn: compareRows
    }))
  },
  getCoreRowModel: getCoreRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getSortedRowModel: getSortedRowModel(),
  autoResetPageIndex: false,
  sortDescFirst: false,
  initialState: {
    pagination: {
      pageSize: pageSize.value,
      pageIndex: 0
    }
  },
  onColumnFiltersChange: (updaterOrValue) => valueUpdater(updaterOrValue, columnFilters),
  onSortingChange: (updaterOrValue) => valueUpdater(updaterOrValue, sorting),
  onGlobalFilterChange: (updaterOrValue) => valueUpdater(updaterOrValue, search),
  state: {
    get columnFilters() {
      return columnFilters.value
    },
    get sorting() {
      return sorting.value
    },
    get globalFilter() {
      return search.value
    }
  }
})

// Identity, not the array itself: a refetch brings the same templates back in a
// brand new one, and that must not move the user.
const rowsKey = computed(() => props.rows.map((row, index) => row.id ?? index).join('|'))

watch([search, rowsKey], () => table.setPageIndex(0))

const filteredRowCount = computed(() => table.getFilteredRowModel().rows.length)

const emptyVariant = computed(() =>
  (props.totalRows ?? props.rows.length) === 0 ? 'first-run' : 'no-results'
)

const handleRowClick = (rowData: Record<string, unknown>) => {
  emit('rowClick', rowData)
}

const TEMPLATES_SEARCH_INPUT_ID = 'templates-search'
</script>

<template>
  <PageToolbar v-if="!props.hideToolbar" :inline-tabs="props.inlineTabs">
    <template v-if="$slots.tabs" #tabs>
      <slot name="tabs" />
    </template>
    <template #search>
      <SearchInput
        :id="TEMPLATES_SEARCH_INPUT_ID"
        v-model="search"
        :placeholder="t('views.templates.filters.search.placeholder')"
        :autofocus="props.autofocusSearch"
      />
    </template>
    <template #filters>
      <slot name="filters-left" />
    </template>
    <template #actions>
      <slot name="filters-right" />
    </template>
  </PageToolbar>

  <div v-if="props.loading" class="flex flex-col gap-4 mt-8">
    <div v-for="n in 4" :key="'skeleton-row-' + n" class="flex gap-2">
      <Skeleton class="h-16 w-47 rounded-l-2xl shrink-0" />
      <Skeleton class="h-16 w-full rounded-r-2xl" />
    </div>
  </div>

  <slot v-else-if="filteredRowCount === 0" name="empty" :variant="emptyVariant">
    <EmptyState
      :kind="props.emptyKind"
      :variant="emptyVariant"
      :searching="search.length > 0"
      @clear-search="search = ''"
    />
  </slot>

  <template v-else>
    <div
      class="grid gap-y-4"
      :style="{
        gridTemplateColumns: headers.map((header) => header.width || 'minmax(0, 1fr)').join(' ')
      }"
      role="table"
    >
      <div role="row" class="grid col-span-full" style="grid-template-columns: subgrid">
        <DataTableHead
          v-for="(header, index) in headers"
          :key="'header-grid-' + index"
          class="h-auto px-4 text-sm text-gray-warm-900"
          role="columnheader"
          :sortable="header.sortable"
          :sorted="table.getColumn(header.key)?.getIsSorted()"
          @togle-sorting="table.getColumn(header.key)?.toggleSorting()"
        >
          {{ header.name }}
        </DataTableHead>
      </div>

      <Tooltip
        v-for="(row, rowIndex) in table.getPaginationRowModel().rows"
        :key="'row-grid-' + rowIndex"
        :delay-duration="300"
      >
        <TooltipTrigger as-child>
          <div
            class="grid col-span-full rounded-2xl group/row"
            style="grid-template-columns: subgrid"
            :class="{
              'cursor-pointer': props.isClickable && !isRowDisabled?.(row.original),
              'cursor-not-allowed': isRowDisabled?.(row.original)
            }"
            :tabindex="0"
            :role="'row'"
            :aria-disabled="isRowDisabled?.(row.original) || undefined"
            @click="
              props.isClickable && !isRowDisabled?.(row.original) && handleRowClick(row.original)
            "
            @keydown.enter="
              props.isClickable && !isRowDisabled?.(row.original) && handleRowClick(row.original)
            "
            @keydown.space.prevent="
              props.isClickable && !isRowDisabled?.(row.original) && handleRowClick(row.original)
            "
          >
            <div
              v-for="(header, cellIndex) in headers"
              :key="'cell-grid-' + rowIndex + '-' + cellIndex"
              class="h-16 flex items-center border-gray-warm-200 min-w-0"
              :class="[
                {
                  'px-4 border-y': cellIndex !== 0,
                  'rounded-l-2xl': cellIndex === 0,
                  'rounded-r-2xl border-r': cellIndex === headers.length - 1
                },
                row.original.id === props.selectedId
                  ? 'bg-brand-100 group-hover/row:bg-brand-200'
                  : 'bg-base-white'
              ]"
              role="cell"
            >
              <slot
                :name="`cell-${header.key}`"
                :value="row.getValue(header.key)"
                :row="row.original"
                :header="header"
              >
                {{ row.getValue(header.key) }}
              </slot>
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent
          v-if="props.disabledTooltip && isRowDisabled?.(row.original)"
          :title="props.disabledTooltip"
        />
      </Tooltip>
    </div>

    <DatatablePagination :table="table" class="mt-4" :page-sizes="props.paginationPageSizes" />
  </template>
</template>
