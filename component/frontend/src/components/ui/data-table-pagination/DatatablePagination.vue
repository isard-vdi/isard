<script setup lang="ts">
import { type Table } from '@tanstack/vue-table'
import { computed } from 'vue'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'

interface DataTablePaginationProps {
  table: Table<any>
  pageSizes?: number[]
}
const props = withDefaults(defineProps<DataTablePaginationProps>(), {
  pageSizes: () => [10, 20, 30, 40, 50]
})
const { table } = props

const visiblePages = computed(() => {
  const currentPage = computed(() => table.getState().pagination.pageIndex + 1)
  const totalPages = computed(() => table.getPageCount())

  if (totalPages.value <= 8) {
    return Array.from({ length: totalPages.value }, (_, i) => ({
      type: 'page',
      value: i + 1
    }))
  }

  // Show elipsis if there are more than 3 pages before the current page, while always showing the first and last page
  const result = []
  result.push({ type: 'page', value: 1 })
  if (currentPage.value > 3) {
    result.push({ type: 'ellipsis', value: null })
  }
  if (currentPage.value > 2) {
    result.push({ type: 'page', value: currentPage.value - 1 })
  }
  if (currentPage.value > 1 && currentPage.value < totalPages.value) {
    result.push({ type: 'page', value: currentPage.value })
  }
  if (currentPage.value < totalPages.value - 1) {
    result.push({ type: 'page', value: currentPage.value + 1 })
  }
  if (currentPage.value < totalPages.value - 2) {
    result.push({ type: 'ellipsis', value: null })
  }
  result.push({ type: 'page', value: totalPages.value })
  return result
})
</script>

<template>
  <div class="flex items-center justify-between">
    <div class="flex items-center space-x-2">
      <div class="text-sm text-muted-foreground">
        {{ table.getFilteredRowModel().rows.length }}
        {{ $t('components.datatable.pagination.rows') }}
      </div>
    </div>
    <!-- Only show pagination if needed -->
    <div
      v-if="table.getFilteredRowModel().rows.length > table.getState().pagination.pageSize"
      class="grow flex justify-center items-center"
    >
      <div class="flex items-center space-x-2">
        <Button
          hierarchy="secondary-gray"
          size="sm"
          icon="chevron-left-double"
          :disabled="!table.getCanPreviousPage()"
          @click="table.setPageIndex(0)"
        >
        </Button>
        <Button
          hierarchy="secondary-gray"
          size="sm"
          :disabled="!table.getCanPreviousPage()"
          @click="table.previousPage()"
        >
          {{ $t('components.datatable.pagination.previous') }}
        </Button>

        <div class="flex items-center space-x-1">
          <template v-for="(page, index) in visiblePages" :key="index">
            <Button
              v-if="page.type === 'page'"
              hierarchy="pagination-button"
              size="sm"
              :disabled="table.getState().pagination.pageIndex === page.value - 1"
              @click="table.setPageIndex(page.value - 1)"
            >
              {{ page.value }}
            </Button>
            <span v-else class="px-2">...</span>
          </template>
        </div>

        <Button
          hierarchy="secondary-gray"
          size="sm"
          :disabled="!table.getCanNextPage()"
          @click="table.nextPage()"
        >
          {{ $t('components.datatable.pagination.next') }}
        </Button>
        <Button
          hierarchy="secondary-gray"
          size="sm"
          icon="chevron-right-double"
          :disabled="!table.getCanNextPage()"
          @click="table.setPageIndex(table.getPageCount() - 1)"
        >
        </Button>
      </div>
    </div>
    <div v-else class="grow"></div>
    <!-- Shown rows selector always visible -->
    <div class="flex items-center space-x-6">
      <div class="flex items-center space-x-2">
        <p class="text-sm font-medium">
          {{ $t('components.datatable.pagination.showing') }}
        </p>
        <Select
          :model-value="`${table.getState().pagination.pageSize}`"
          @update:model-value="table.setPageSize"
        >
          <SelectTrigger class="h-8 w-[70px] bg-base-white">
            <SelectValue :placeholder="`${table.getState().pagination.pageSize}`" />
          </SelectTrigger>
          <SelectContent side="top">
            <SelectItem v-for="pageSize in props.pageSizes" :key="pageSize" :value="`${pageSize}`">
              {{ pageSize }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  </div>
</template>
