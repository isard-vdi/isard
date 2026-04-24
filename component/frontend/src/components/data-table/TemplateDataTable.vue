<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  useVueTable,
  getCoreRowModel,
  getPaginationRowModel,
  type ColumnFiltersState,
  getFilteredRowModel
} from '@tanstack/vue-table'

import { valueUpdater } from '@/lib/utils'

import templatesEmptyImg from '@/assets/img/templates-empty.svg'

import { Icon } from '@/components/icon'
import DatatablePagination from '@/components/ui/data-table-pagination/DatatablePagination.vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { InputField } from '@/components/input-field'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'

const { t } = useI18n()

export interface HeaderCell {
  name: string
  key: string
  width?: string
}

interface Props {
  headers: HeaderCell[]
  rows: Record<string, unknown>[]
  pageSize?: number
  paginationPageSizes?: number[]
  loading?: boolean
  isClickable: boolean
  selectedId?: string
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 10,
  paginationPageSizes: undefined,
  loading: false,
  isClickable: false
})

const emit = defineEmits<{
  rowClick: [Record<string, unknown>]
}>()

const pageSize = computed(() => props.pageSize ?? 10)
const columnFilters = ref<ColumnFiltersState>([])
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
  getFilteredRowModel: getFilteredRowModel(),
  initialState: {
    pagination: {
      pageSize: pageSize.value,
      pageIndex: 0
    }
  },
  onColumnFiltersChange: (updaterOrValue) => valueUpdater(updaterOrValue, columnFilters),
  onGlobalFilterChange: (updaterOrValue) => valueUpdater(updaterOrValue, globalFilter),
  state: {
    get columnFilters() {
      return columnFilters.value
    },
    get globalFilter() {
      return globalFilter.value
    }
  }
})

const handleRowClick = (rowData: Record<string, unknown>) => {
  emit('rowClick', rowData)
}
</script>

<template>
  <div class="flex mb-4 gap-2">
    <slot name="filters-left" />

    <InputField
      ref="searchRef"
      class="h-min w-full max-w-120 ml-auto"
      :placeholder="t('views.templates.filters.search.placeholder')"
      icon="search-lg"
      :model-value="globalFilter ?? ''"
      @update:model-value="(value: string) => (globalFilter = String(value))"
    />
    <slot name="filters-right" />
  </div>

  <div v-if="props.loading" class="flex flex-col gap-4 mt-8">
    <div v-for="n in 4" :key="'skeleton-row-' + n" class="flex gap-2">
      <Skeleton class="h-16 w-47 rounded-l-2xl shrink-0" />
      <Skeleton class="h-16 w-full rounded-r-2xl" />
    </div>
  </div>

  <Empty v-else-if="props.rows.length === 0" class="md:flex-row-reverse mt-16">
    <EmptyHeader>
      <EmptyMedia variant="default" class="select-none pointer-events-none">
        <img :src="templatesEmptyImg" />
      </EmptyMedia>
    </EmptyHeader>
    <div class="flex flex-col items-start text-left gap-4">
      <EmptyTitle class="text-[60px] leading-[72px] font-bold text-gray-warm-950">{{
        t('components.empty.title', { kind: t('domains.templates', 0) })
      }}</EmptyTitle>
      <EmptyDescription class="text-[18px]! text-gray-warm-900">{{
        t('components.empty.description', { kind: t('domains.templates', 0) })
      }}</EmptyDescription>
    </div>
  </Empty>

  <template v-else>
    <div
      class="grid gap-y-4"
      :style="{
        gridTemplateColumns: headers.map((header) => header.width || 'minmax(0, 1fr)').join(' ')
      }"
    >
      <div class="grid col-span-full" style="grid-template-columns: subgrid">
        <div
          v-for="(header, index) in headers"
          :key="'header-grid-' + index"
          class="text-sm font-semibold text-gray-warm-900 px-4"
        >
          {{ header.name }}
        </div>
      </div>

      <div
        v-for="(row, rowIndex) in table.getPaginationRowModel().rows"
        :key="'row-grid-' + rowIndex"
        class="grid col-span-full rounded-2xl group/row"
        style="grid-template-columns: subgrid"
        :class="{ 'cursor-pointer': props.isClickable }"
        :tabindex="props.isClickable ? 0 : undefined"
        :role="props.isClickable ? 'button' : undefined"
        @click="props.isClickable && handleRowClick(row.original)"
        @keydown.enter="props.isClickable && handleRowClick(row.original)"
        @keydown.space.prevent="props.isClickable && handleRowClick(row.original)"
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
    </div>

    <DatatablePagination :table="table" class="mt-4" :page-sizes="props.paginationPageSizes" />
  </template>
</template>
