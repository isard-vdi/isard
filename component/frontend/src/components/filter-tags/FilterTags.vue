<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'

export interface FilterOption {
  value: string
  label: string
  count?: number
}

export interface FilterCategory {
  key: string
  label: string
  options: FilterOption[]
}

interface Props {
  categories: FilterCategory[]
  class?: string
}

const props = defineProps<Props>()

const model = defineModel<Record<string, string[]>>({ required: true })

const { t } = useI18n()

const selectedOf = (categoryKey: string) => model.value[categoryKey] ?? []

const tags = computed(() =>
  props.categories.flatMap((category) =>
    category.options
      .filter((option) => selectedOf(category.key).includes(option.value))
      .map((option) => ({ categoryKey: category.key, ...option }))
  )
)

const isSelected = (categoryKey: string, value: string) => selectedOf(categoryKey).includes(value)

const setSelected = (categoryKey: string, values: string[]) => {
  model.value = { ...model.value, [categoryKey]: values }
}

const toggle = (categoryKey: string, value: string) => {
  const selected = selectedOf(categoryKey)
  setSelected(
    categoryKey,
    selected.includes(value)
      ? selected.filter((selectedValue) => selectedValue !== value)
      : [...selected, value]
  )
}

const clear = () => {
  model.value = Object.fromEntries(props.categories.map((category) => [category.key, []]))
}

const label = computed(() =>
  tags.value.length
    ? t('components.filters.toggle-active', { count: tags.value.length })
    : t('components.filters.toggle')
)
</script>

<template>
  <DropdownMenu>
    <div
      :class="
        cn(
          // 42px is what a size-md Button and an InputField measure, so the
          // control lines up with the rest of a toolbar row.
          'inline-flex h-[42px] w-fit max-w-full flex-row items-center gap-1.5 overflow-hidden rounded-md border border-gray-warm-300 bg-base-white px-1.5',
          'shadow-[0px_1px_2px_0px_rgba(16,24,40,0.05)] transition-[color,box-shadow]',
          'focus-within:border-secondary-3-400 focus-within:ring-4 focus-within:ring-brand focus-within:outline-hidden',
          props.class
        )
      "
    >
      <!-- Before the tags: growing them must not push the trigger sideways.
           No ring of its own: the wrapper already rings on focus-within, and a
           second one reads as a double border (overflow-hidden clips it too). -->
      <DropdownMenuTrigger
        :aria-label="label"
        class="inline-flex h-7 shrink-0 cursor-pointer flex-row items-center gap-1.5 rounded-[6px] px-1.5 text-md font-regular text-gray-warm-600 hover:bg-gray-warm-50 focus:bg-gray-warm-100 focus:outline-none"
      >
        <Icon name="filter-funnel-02" size="sm" stroke-color="gray-warm-500" />
        <span v-if="tags.length === 0">{{ t('components.filters.toggle') }}</span>
        <Icon name="chevron-down" size="sm" stroke-color="gray-warm-500" />
      </DropdownMenuTrigger>

      <span
        v-for="tag in tags"
        :key="`${tag.categoryKey}:${tag.value}`"
        class="inline-flex h-7 shrink-0 items-center gap-0.5 rounded-[6px] bg-gray-warm-100 pl-2 pr-1 text-sm font-medium text-gray-warm-800"
      >
        {{ tag.label }}
        <button
          type="button"
          class="group flex items-center justify-center rounded-xs p-0.5 hover:bg-error-100 focus:bg-error-100 focus:outline-none"
          :aria-label="t('components.filters.remove', { name: tag.label })"
          @click="toggle(tag.categoryKey, tag.value)"
        >
          <Icon
            name="x-close"
            size="sm"
            stroke-color="gray-warm-500"
            class="group-hover:text-error-600"
          />
        </button>
      </span>
    </div>

    <!-- The popper anchors on the trigger, which sits inset inside the wrapper:
         7px in from its left border, and 7px up from its bottom one. Both
         offsets add that back, so the menu lines up with the visible control
         instead of hanging over it. -->
    <DropdownMenuContent align="start" :align-offset="-7" :side-offset="11" class="min-w-44">
      <DropdownMenuSub v-for="category in props.categories" :key="category.key">
        <DropdownMenuSubTrigger>
          {{ category.label }}
          <span v-if="selectedOf(category.key).length" class="ml-2 text-xs text-gray-warm-500">
            {{ selectedOf(category.key).length }}
          </span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent class="min-w-44">
          <!-- Multi-select: a checked item must not close the menu. -->
          <DropdownMenuCheckboxItem
            v-for="option in category.options"
            :key="option.value"
            :model-value="isSelected(category.key, option.value)"
            @select.prevent
            @update:model-value="toggle(category.key, option.value)"
          >
            {{ option.label }}
            <span v-if="option.count !== undefined" class="ml-auto pl-4 text-xs text-gray-warm-500">
              {{ option.count }}
            </span>
          </DropdownMenuCheckboxItem>
        </DropdownMenuSubContent>
      </DropdownMenuSub>

      <template v-if="tags.length">
        <DropdownMenuSeparator />
        <DropdownMenuItem @select="clear">
          <Icon name="x-close" size="sm" stroke-color="gray-warm-500" class="mr-2" />
          {{ t('components.filters.clear') }}
        </DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
