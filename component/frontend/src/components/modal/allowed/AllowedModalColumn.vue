<script setup lang="ts">
import { computed } from 'vue'
import { useFilter } from 'reka-ui'
import { InputField } from '@/components/input-field'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import AllowedModalItem from './AllowedModalItem.vue'
import type { AllowedOption } from '.'

interface Props {
  title: string
  items: AllowedOption[]
  selected: string[]
  indeterminate?: string[]
  activeId?: string | null
  loading?: boolean
  disabled?: boolean
  searchPlaceholder: string
  emptyText: string
  notFoundText: string
  footerText?: string
  selectAll?: boolean
  selectAllLabel?: string
  selectAllCountLabel?: string
  selectAllChecked?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  indeterminate: () => [],
  activeId: null,
  loading: false,
  disabled: false,
  footerText: '',
  selectAll: false,
  selectAllLabel: '',
  selectAllCountLabel: '',
  selectAllChecked: false
})

const emit = defineEmits<{
  (e: 'toggle' | 'select', value: string): void
  (e: 'toggle-all', selectAll: boolean): void
}>()

const search = defineModel<string>('search', { default: '' })

const { contains } = useFilter({ sensitivity: 'base' })

const filteredItems = computed(() => {
  if (!search.value) return props.items
  return props.items.filter(
    (item) =>
      contains(item.label, search.value) ||
      (item.subLabel !== undefined && contains(item.subLabel, search.value))
  )
})

const checkedState = (value: string): boolean | 'indeterminate' => {
  if (props.selected.includes(value)) return true
  if (props.indeterminate.includes(value)) return 'indeterminate'
  return false
}

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
    <div class="flex h-6 shrink-0 flex-row items-center gap-2 px-2">
      <h3
        :class="[
          'min-w-0 truncate text-sm font-semibold text-gray-warm-900',
          props.disabled && 'opacity-60'
        ]"
      >
        {{ props.title }}
      </h3>
    </div>

    <InputField
      :model-value="search"
      icon="search-sm"
      :placeholder="props.searchPlaceholder"
      :disabled="props.disabled"
      class="shrink-0"
      @update:model-value="(value) => (search = String(value))"
    />

    <div
      class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-gray-warm-200 bg-base-white"
    >
      <div
        v-if="props.selectAll"
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

      <ScrollArea class="min-h-0 flex-1">
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
            <AllowedModalItem
              v-for="item in filteredItems"
              :key="item.value"
              :label="item.label"
              :sub-label="item.subLabel"
              :value="item.value"
              :avatar="item.avatar"
              :icon="item.icon"
              :checked="checkedState(item.value)"
              :active="item.value === props.activeId"
              :disabled="props.disabled"
              @update:checked="emit('toggle', item.value)"
              @select="emit('select', item.value)"
            >
              <template v-if="$slots.actions" #actions>
                <slot name="actions" :item="item" />
              </template>
            </AllowedModalItem>

            <p v-if="props.footerText" class="px-2 py-3 text-center text-sm text-gray-warm-500">
              {{ props.footerText }}
            </p>
          </template>
        </div>
      </ScrollArea>
    </div>
  </div>
</template>
