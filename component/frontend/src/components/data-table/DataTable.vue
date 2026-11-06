<script setup lang="ts">
import { ref, computed, watch, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HTMLAttributes } from 'vue'
import { createReusableTemplate, useResizeObserver } from '@vueuse/core'

const { t } = useI18n()

import type { ColumnDef, SortingState } from '@tanstack/vue-table'
import {
  useVueTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  getFilteredRowModel
} from '@tanstack/vue-table'

import { cn, valueUpdater } from '@/lib/utils'

import DatatablePagination from '@/components/ui/data-table-pagination/DatatablePagination.vue'
import {
  DataTableBackground,
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHeaderRow,
  DataTableRow,
  DataTableHead,
  DataTableEmpty
} from '@/components/ui/data-table'
import InputField from '@/components/input-field/InputField.vue'

export interface HeaderCell {
  name: string
  key: string

  sortable?: boolean

  headerClass?: string
  /** Merged onto every body cell of this column, after the table-wide `cellClass`. */
  cellClass?: string
  width?: string
  /** Pin the column against the table's horizontal scroll. */
  sticky?: 'left'
}

export type DataTableDensity = 'comfortable' | 'compact'

// `cellClass` still wins over the density defaults.
const DENSITY: Record<DataTableDensity, { container: string; head: string; cell: string }> = {
  comfortable: {
    container: '',
    head: '',
    cell: ''
  },
  compact: {
    container: 'py-3 px-5 gap-2',
    head: 'h-8 px-2.5',
    cell: 'h-10 px-2.5 py-2'
  }
}

interface Props {
  headers: HeaderCell[]
  rows: Record<string, unknown>[]
  pageSize?: number
  rowClass?: HTMLAttributes['class']
  higlightedRowId?: string
  isClickable: boolean
  defaultSort?: { key: string; desc?: boolean }
  cellClass?: HTMLAttributes['class']
  density?: DataTableDensity
  stickyHeader?: boolean
  stickyFooter?: boolean
}

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10,
  higlightedRowId: undefined,
  isClickable: false,
  defaultSort: undefined,
  cellClass: undefined,
  density: 'comfortable',
  stickyHeader: false,
  stickyFooter: false
})

const density = computed(() => DENSITY[props.density] ?? DENSITY.comfortable)

const emit = defineEmits<{
  rowClick: [(typeof props.rows)[number]]
}>()

const pageSize = computed(() => props.pageSize ?? 10)

const sorting = ref<SortingState>(
  props.defaultSort ? [{ id: props.defaultSort.key, desc: props.defaultSort.desc ?? false }] : []
)

const globalFilter = ref('')

const table = useVueTable({
  get data() {
    return props.rows
  },
  get columns() {
    return props.headers.map((header) => ({
      accessorKey: header.key,
      header: header.name
    }))
  },
  getCoreRowModel: getCoreRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  initialState: {
    pagination: {
      pageSize: pageSize.value,
      pageIndex: 0
    }
  },
  getSortedRowModel: getSortedRowModel(),
  onSortingChange: (updaterOrValue) => valueUpdater(updaterOrValue, sorting),
  getFilteredRowModel: getFilteredRowModel(),

  onGlobalFilterChange: (updaterOrValue) => valueUpdater(updaterOrValue, globalFilter),
  state: {
    get sorting() {
      return sorting.value
    },
    get globalFilter() {
      return globalFilter.value
    }
  },
  autoResetAll: false
})

watch(pageSize, (value) => {
  table.setPageSize(value)
})

watch(
  () => table.getPageCount(),
  (count) => {
    const lastPage = Math.max(count - 1, 0)
    if (table.getState().pagination.pageIndex > lastPage) table.setPageIndex(lastPage)
  }
)

const templateCols = computed(() =>
  props.headers.map((header) => header.width || 'minmax(var(--spacing-48), 1fr)')
)

const [DefineHeaderRow, ReuseHeaderRow] = createReusableTemplate<{ sizer?: boolean }>()

const bodyGrid = useTemplateRef('bodyGrid')
const measuredCols = ref<string>()

const measureColumns = () => {
  const el = bodyGrid.value?.el
  if (!props.stickyHeader || !el) return
  measuredCols.value = getComputedStyle(el).gridTemplateColumns
}

useResizeObserver(() => (props.stickyHeader ? bodyGrid.value?.el : undefined), measureColumns)
watch(
  [() => props.stickyHeader, () => props.headers, () => table.getPaginationRowModel().rows],
  measureColumns,
  { flush: 'post' }
)

const headerTemplateCols = computed(() =>
  measuredCols.value ? [measuredCols.value] : templateCols.value
)

const handleRowClick = (rowData: Record<string, unknown>) => {
  emit('rowClick', rowData)
}

// `DataTableBackground` already wraps the grid in an `overflow-x-auto`
// div, and rows are real grid items (`grid-cols-subgrid`) rather than
// `display: contents`, so a sticky cell resolves against that scroller.
// It needs an opaque background, which would otherwise swallow the row
// hover — pass `row-class="group"` to keep the hover working. The column's
// own `headerClass`/`cellClass` go after these, so it can tint the pinned column.
const STICKY_HEAD_CLASSES = 'sticky left-0 z-20 bg-base-white'
const STICKY_CELL_CLASSES = 'sticky left-0 z-10 bg-base-white group-hover:bg-gray-warm-50'

// Keeps the header's widths in the body grid once the visible header leaves it.
const HEADER_SIZER_CLASSES = 'invisible h-0 overflow-hidden border-0'
</script>

<template>
  <div class="contents">
    <DefineHeaderRow v-slot="{ sizer }">
      <DataTableHeaderRow :class="sizer && HEADER_SIZER_CLASSES" :aria-hidden="sizer || undefined">
        <DataTableHead
          v-for="(header, index) in headers"
          :key="'header-' + index"
          :class="
            cn(density.head, header.sticky === 'left' && STICKY_HEAD_CLASSES, header.headerClass)
          "
          :sortable="header.sortable"
          :sorted="table.getColumn(header.key)?.getIsSorted()"
          @togle-sorting="table.getColumn(header.key)?.toggleSorting()"
        >
          <slot :name="`head-${header.key}`" :header="header">
            {{ header.name }}
          </slot>
        </DataTableHead>
      </DataTableHeaderRow>
    </DefineHeaderRow>

    <DataTableBackground
      v-bind="$attrs"
      :class="density.container"
      :sticky-footer="props.stickyFooter"
    >
      <template v-if="props.stickyHeader" #header>
        <DataTable :template-cols="headerTemplateCols">
          <ReuseHeaderRow />
        </DataTable>
      </template>

      <DataTable ref="bodyGrid" :template-cols="templateCols">
        <ReuseHeaderRow :sizer="props.stickyHeader" />

        <DataTableBody>
          <template v-if="table.getRowModel().rows?.length">
            <DataTableRow
              v-for="(row, rowIndex) in table.getPaginationRowModel().rows"
              :key="row.id"
              :class="
                cn(props.rowClass, {
                  'bg-brand-100 hover:bg-brand-200':
                    row.original.id && row.original.id === props.higlightedRowId,
                  'cursor-pointer': props.isClickable === true
                })
              "
              :tabindex="props.isClickable ? 0 : undefined"
              @click="props.isClickable && handleRowClick(row.original)"
              @keydown.enter="props.isClickable && handleRowClick(row.original)"
              @keydown.space.prevent="props.isClickable && handleRowClick(row.original)"
            >
              <DataTableCell
                v-for="(header, cellIndex) in headers"
                :key="'cell-' + rowIndex + '-' + cellIndex"
                :class="
                  cn(
                    density.cell,
                    props.cellClass,
                    header.sticky === 'left' && STICKY_CELL_CLASSES,
                    header.cellClass
                  )
                "
              >
                <slot
                  :name="`cell-${header.key}`"
                  :value="row.getValue(header.key)"
                  :row="row.original"
                  :header="header"
                >
                  {{ row.getValue(header.key) }}
                </slot>
              </DataTableCell>
            </DataTableRow>
          </template>

          <DataTableEmpty v-else>
            <slot name="empty">
              {{ t('components.datatable.empty') }}
            </slot>
          </DataTableEmpty>
        </DataTableBody>
      </DataTable>

      <template #pagination>
        <DatatablePagination :table="table"> </DatatablePagination>
      </template>
    </DataTableBackground>
  </div>
</template>
