<script setup lang="ts">
import { ref, computed } from 'vue'
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
  width?: string
}

interface Props {
  headers: HeaderCell[]
  rows: Record<string, unknown>[]
  pageSize?: number
  rowClass?: HTMLAttributes['class']
  higlightedRowId?: string
  isClickable: boolean
  cellClass: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10,
  higlightedRowId: undefined,
  isClickable: false
})

const emit = defineEmits<{
  rowClick: [(typeof props.rows)[number]]
}>()

const pageSize = computed(() => props.pageSize ?? 10)

const sorting = ref<SortingState>([])

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

const handleRowClick = (rowData: Record<string, unknown>) => {
  emit('rowClick', rowData)
}
</script>

<template>
  <DataTableBackground>
    <DataTable
      :template-cols="headers.map((header) => header.width || 'minmax(var(--spacing-48), 1fr)')"
    >
      <DataTableHeaderRow>
        <DataTableHead
          v-for="(header, index) in headers"
          :key="'header-' + index"
          :class="header.headerClass"
          :sortable="header.sortable"
          :sorted="table.getColumn(header.key)?.getIsSorted()"
          @togle-sorting="table.getColumn(header.key)?.toggleSorting()"
        >
          {{ header.name }}
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
              :class="props.cellClass"
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
