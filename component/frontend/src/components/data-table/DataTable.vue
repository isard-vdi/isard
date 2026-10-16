<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HTMLAttributes } from 'vue'

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
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10,
  higlightedRowId: undefined,
  isClickable: false,
  defaultSort: undefined,
  cellClass: undefined,
  density: 'comfortable'
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

const handleRowClick = (rowData: Record<string, unknown>) => {
  emit('rowClick', rowData)
}

// `DataTableBackground` already wraps the grid in an `overflow-x-auto`
// div, and rows are real grid items (`grid-cols-subgrid`) rather than
// `display: contents`, so a sticky cell resolves against that scroller.
// It needs an opaque background, which would otherwise swallow the row
// hover — pass `row-class="group"` to keep the hover working.
const STICKY_HEAD_CLASSES = 'sticky left-0 z-20 bg-base-white'
const STICKY_CELL_CLASSES = 'sticky left-0 z-10 bg-base-white group-hover:bg-gray-warm-50'
</script>

<template>
  <DataTableBackground :class="density.container">
    <DataTable
      :template-cols="headers.map((header) => header.width || 'minmax(var(--spacing-48), 1fr)')"
    >
      <DataTableHeaderRow>
        <DataTableHead
          v-for="(header, index) in headers"
          :key="'header-' + index"
          :class="
            cn(density.head, header.headerClass, header.sticky === 'left' && STICKY_HEAD_CLASSES)
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
                  header.cellClass,
                  header.sticky === 'left' && STICKY_CELL_CLASSES
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
</template>
