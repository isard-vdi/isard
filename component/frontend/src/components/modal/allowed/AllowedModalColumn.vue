<script setup lang="ts">
import { computed, ref, type ComponentPublicInstance } from 'vue'
import { useFilter } from 'reka-ui'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { Icon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import AllowedModalItem from './AllowedModalItem.vue'
import type { AllowedOption } from '.'

interface Props {
  title: string
  icon?: string | undefined
  items: AllowedOption[]
  selected: string[]
  loading?: boolean
  disabled?: boolean
  selectable?: boolean // When false the rows cannot be toggled and there is no select-all header.
  searchPlaceholder: string
  emptyText: string
  notFoundText: string
  footerText?: string
  filterLocally?: boolean // When false the caller filters the items itself, e.g. with a server-side search.
  selectAll?: boolean
  selectAllLabel?: string
  selectAllCountLabel?: string
  selectAllChecked?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  icon: undefined,
  loading: false,
  disabled: false,
  selectable: true,
  footerText: '',
  filterLocally: true,
  selectAll: false,
  selectAllLabel: '',
  selectAllCountLabel: '',
  selectAllChecked: false
})

const emit = defineEmits<{
  (e: 'toggle', value: string): void
  (e: 'toggle-all', selectAll: boolean): void
}>()

const search = defineModel<string>('search', { default: '' })

const { contains } = useFilter({ sensitivity: 'base' })

const filteredItems = computed(() => {
  if (!search.value || !props.filterLocally) return props.items
  return props.items.filter(
    (item) =>
      contains(item.label, search.value) ||
      (item.subLabel !== undefined && contains(item.subLabel, search.value))
  )
})

const ROW_ESTIMATE = 56

const scrollArea = ref<InstanceType<typeof ScrollArea>>()

const rowVirtualizer = useVirtualizer(
  computed(() => ({
    count: filteredItems.value.length,
    getScrollElement: () => scrollArea.value?.viewport ?? null,
    estimateSize: () => ROW_ESTIMATE,
    overscan: 8,
    getItemKey: (index: number) => filteredItems.value[index]?.value ?? index
  }))
)

const virtualRows = computed(() =>
  rowVirtualizer.value.getVirtualItems().flatMap((row) => {
    const item = filteredItems.value[row.index]
    return item ? [{ row, item }] : []
  })
)

const measureRow = (el: Element | ComponentPublicInstance | null) => {
  if (el instanceof Element) rowVirtualizer.value.measureElement(el)
}

const selectedSet = computed(() => new Set(props.selected))

const masterState = computed<boolean | 'indeterminate'>(() => {
  if (props.selectAllChecked) return true
  return props.selected.length > 0 ? 'indeterminate' : false
})

const masterDisabled = computed(() => props.loading || props.disabled || props.items.length === 0)

const toggleAll = () => {
  if (masterDisabled.value) return
  emit('toggle-all', !props.selectAllChecked)
}
</script>

<template>
  <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
    <div
      :class="
        cn(
          'flex h-6 shrink-0 flex-row text-gray-warm-900 items-center gap-2 px-2',
          props.disabled && 'opacity-60'
        )
      "
    >
      <Icon
        v-if="props.icon"
        :name="props.icon"
        size="sm"
        stroke-color="currentColor"
        class="shrink-0"
        aria-hidden="true"
      />
      <h3 class="min-w-0 truncate text-sm font-semibold">
        {{ props.title }}
      </h3>
    </div>

    <div class="flex shrink-0 flex-row gap-2">
      <InputField
        :model-value="search"
        icon="search-sm"
        :placeholder="props.searchPlaceholder"
        :disabled="props.disabled"
        class="shrink-0 grow basis-3/5"
        @update:model-value="(value) => (search = String(value))"
      />
      <slot name="search-actions" />
    </div>

    <div
      class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-gray-warm-200 bg-base-white"
    >
      <div
        v-if="props.selectAll && props.selectable"
        :class="
          cn(
            'flex min-h-10 shrink-0 select-none flex-row items-center gap-2 border-b border-gray-warm-200 bg-gray-warm-50 px-3 py-2.5',
            masterDisabled
              ? 'cursor-not-allowed opacity-60'
              : 'cursor-pointer hover:bg-gray-warm-100'
          )
        "
        data-slot="select-all-row"
        @click="toggleAll"
      >
        <span class="flex shrink-0 items-center" @click.stop>
          <Checkbox
            :model-value="masterState"
            :indeterminate="masterState === 'indeterminate'"
            :disabled="masterDisabled"
            :aria-label="props.selectAllLabel"
            data-slot="select-all"
            size="md"
            class="bg-base-white"
            @update:model-value="toggleAll"
          />
        </span>
        <span class="min-w-0 truncate text-sm font-semibold text-gray-warm-700">
          {{ props.selectAllLabel }}
        </span>
        <span
          v-if="props.selectAllCountLabel"
          class="ml-auto shrink-0 text-xs font-medium text-gray-warm-500"
        >
          {{ props.selectAllCountLabel }}
        </span>
      </div>

      <ScrollArea ref="scrollArea" class="min-h-0 flex-1">
        <div class="flex flex-col gap-1 p-1" role="listbox">
          <template v-if="props.loading">
            <Skeleton v-for="index in 3" :key="index" class="h-12 w-full" />
          </template>

          <p
            v-else-if="props.items.length === 0"
            class="px-2 py-6 text-center text-sm text-gray-warm-500"
          >
            {{ props.emptyText }}
          </p>

          <p
            v-else-if="filteredItems.length === 0"
            class="px-2 py-6 text-center text-sm text-gray-warm-500"
          >
            {{ props.notFoundText }}
          </p>

          <template v-else>
            <div class="relative w-full" :style="{ height: `${rowVirtualizer.getTotalSize()}px` }">
              <div
                v-for="{ row, item } in virtualRows"
                :key="row.key"
                :ref="measureRow"
                :data-index="row.index"
                class="absolute left-0 top-0 w-full pb-1"
                :style="{ transform: `translateY(${row.start}px)` }"
              >
                <AllowedModalItem
                  :label="item.label"
                  :sub-label="item.subLabel"
                  :value="item.value"
                  :avatar="item.avatar"
                  :icon="item.icon"
                  :checked="selectedSet.has(item.value)"
                  :disabled="props.disabled"
                  :selectable="props.selectable"
                  :aria-setsize="filteredItems.length"
                  :aria-posinset="row.index + 1"
                  @update:checked="emit('toggle', item.value)"
                >
                  <template v-if="$slots.actions" #actions>
                    <slot name="actions" :item="item" />
                  </template>
                </AllowedModalItem>
              </div>
            </div>

            <p v-if="props.footerText" class="px-2 py-3 text-center text-sm text-gray-warm-500">
              {{ props.footerText }}
            </p>
          </template>
        </div>
      </ScrollArea>
    </div>
  </div>
</template>
