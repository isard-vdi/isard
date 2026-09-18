<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
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
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import FilterTag from './FilterTag.vue'
import { filterToneStyle, type FilterTone } from '.'

export interface FilterOption {
  value: string
  label: string
  count?: number
  tone?: FilterTone
  icon?: string
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
  panelOpen.value = false
}

const label = computed(() =>
  tags.value.length
    ? t('components.filters.toggle-active', { count: tags.value.length })
    : t('components.filters.toggle')
)

const control = ref<HTMLElement | null>(null)
const hiddenCount = ref(0)
const panelOpen = ref(false)

const queryTags = () =>
  Array.from(control.value?.querySelectorAll<HTMLElement>('[data-filter-tag]') ?? [])

const GAP = 6
const PADDING = 6
const BORDER = 1
const SLACK = 2

const measure = (pass = 0) => {
  const element = control.value
  if (!element) return

  const trigger = element.querySelector<HTMLElement>('[data-filter-trigger]')
  if (!trigger) return

  const lastWidth = element.style.width
  element.style.width = ''
  element.style.paddingRight = ''

  const actionsWidth = element.querySelector<HTMLElement>('[data-filter-actions]')?.offsetWidth ?? 0
  const reserved = actionsWidth > 0 ? actionsWidth + GAP : 0

  const paddingRight = PADDING + reserved
  element.style.paddingRight = `${paddingRight}px`

  const firstRowTop = trigger.offsetTop
  const tagElements = queryTags()
  const onFirstRow = tagElements.filter((tag) => tag.offsetTop <= firstRowTop)
  const hidden = tagElements.length - onFirstRow.length

  // With tags left over the box ends at its last tag: stretched to the toolbar
  // instead, it would strand the buttons behind a hole of empty space.
  const last = onFirstRow.at(-1) ?? trigger
  const rowEnd = last.getBoundingClientRect().right - element.getBoundingClientRect().left
  const width = hidden ? `${Math.ceil(rowEnd) + paddingRight + BORDER + SLACK}px` : ''

  const settled = hidden === hiddenCount.value && width === lastWidth
  hiddenCount.value = hidden
  element.style.width = width

  if (!settled && pass < 3) nextTick(() => requestAnimationFrame(() => measure(pass + 1)))
}

useResizeObserver(control, () => measure())

useResizeObserver(
  () => control.value?.parentElement,
  () => measure()
)

const observedTags = shallowRef<HTMLElement[]>([])

useResizeObserver(observedTags, () => measure())

watch(
  tags,
  () =>
    nextTick(() => {
      observedTags.value = queryTags()
      measure()
    }),
  { immediate: true }
)
</script>

<template>
  <div
    ref="control"
    :class="
      cn(
        'relative inline-flex h-[42px] w-fit max-w-full flex-row flex-wrap content-start items-center gap-1.5 overflow-hidden rounded-md border border-gray-warm-300 bg-base-white px-1.5 py-[7px]',
        'shadow-[0px_1px_2px_0px_rgba(16,24,40,0.05)] transition-[color,box-shadow]',
        'focus-within:border-secondary-3-400 focus-within:ring-4 focus-within:ring-brand focus-within:outline-hidden',
        props.class
      )
    "
  >
    <DropdownMenu>
      <DropdownMenuTrigger
        data-filter-trigger
        :aria-label="label"
        class="inline-flex h-7 shrink-0 cursor-pointer flex-row items-center gap-1.5 rounded-[6px] px-1.5 text-md font-regular text-gray-warm-600 hover:bg-gray-warm-50 focus:bg-gray-warm-100 focus:outline-none"
      >
        <Icon name="filter-funnel-02" size="sm" stroke-color="gray-warm-500" />
        <span v-if="tags.length === 0">{{ t('components.filters.toggle') }}</span>
        <Icon name="chevron-down" size="sm" stroke-color="gray-warm-500" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" :align-offset="-7" :side-offset="11" class="min-w-44">
        <DropdownMenuSub v-for="category in props.categories" :key="category.key">
          <DropdownMenuSubTrigger>
            {{ category.label }}
            <span v-if="selectedOf(category.key).length" class="ml-2 text-xs text-gray-warm-500">
              {{ selectedOf(category.key).length }}
            </span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent class="min-w-44">
            <DropdownMenuCheckboxItem
              v-for="option in category.options"
              :key="option.value"
              :model-value="isSelected(category.key, option.value)"
              class="gap-2 pl-2 [&>span:first-child]:hidden"
              @select.prevent
              @update:model-value="toggle(category.key, option.value)"
            >
              <span
                aria-hidden="true"
                :class="
                  cn(
                    'flex size-4 shrink-0 items-center justify-center rounded-sm border',
                    isSelected(category.key, option.value)
                      ? 'border-brand-700 bg-brand-700'
                      : 'border-input bg-base-white'
                  )
                "
              >
                <Icon
                  v-if="isSelected(category.key, option.value)"
                  name="check"
                  size="xs"
                  stroke-color="base-white"
                />
              </span>
              <span class="flex w-full items-center gap-1.5">
                <Icon
                  v-if="option.icon"
                  :name="option.icon"
                  size="sm"
                  :stroke-color="filterToneStyle(option.tone).iconColor"
                  aria-hidden="true"
                  class="shrink-0"
                />
                <span class="truncate">{{ option.label }}</span>
                <span
                  v-if="option.count !== undefined"
                  class="ml-auto shrink-0 pl-4 text-xs tabular-nums text-gray-warm-500"
                >
                  {{ option.count }}
                </span>
              </span>
            </DropdownMenuCheckboxItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <template v-if="tags.length">
          <DropdownMenuSeparator />
          <DropdownMenuItem
            class="text-gray-warm-700 hover:bg-error-100 hover:text-error-800 focus:bg-error-100 focus:text-error-800"
            @select="clear"
          >
            <Icon name="x-circle" size="sm" stroke-color="" aria-hidden="true" />
            {{ t('components.filters.clear') }}
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>

    <FilterTag
      v-for="(tag, index) in tags"
      :key="`${tag.categoryKey}:${tag.value}`"
      data-filter-tag
      :inert="index >= tags.length - hiddenCount"
      :label="tag.label"
      :count="tag.count"
      :tone="tag.tone"
      :icon="tag.icon"
      @remove="toggle(tag.categoryKey, tag.value)"
    />

    <Popover v-model:open="panelOpen">
      <PopoverAnchor as-child>
        <span class="pointer-events-none absolute inset-0" aria-hidden="true" />
      </PopoverAnchor>

      <div
        data-filter-actions
        class="absolute top-1/2 right-1.5 flex -translate-y-1/2 flex-row items-center gap-1"
      >
        <PopoverTrigger
          v-if="hiddenCount > 0 || panelOpen"
          :aria-label="t('components.filters.show-all', { count: tags.length })"
          class="inline-flex h-7 shrink-0 cursor-pointer items-center rounded-[6px] bg-gray-warm-100 px-1.5 text-sm font-semibold text-gray-warm-700 tabular-nums hover:bg-gray-warm-200 focus:bg-gray-warm-200 focus:outline-none"
        >
          +{{ hiddenCount }}
        </PopoverTrigger>

        <TooltipProvider v-if="tags.length">
          <Tooltip>
            <TooltipTrigger as-child>
              <button
                type="button"
                :aria-label="t('components.filters.clear')"
                class="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-[6px] text-gray-warm-500 hover:bg-error-100 hover:text-error-800 focus:bg-error-100 focus:text-error-800 focus:outline-none"
                @click="clear"
              >
                <Icon name="x-circle" size="sm" stroke-color="" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent :title="t('components.filters.clear')" side="top" />
          </Tooltip>
        </TooltipProvider>
      </div>

      <PopoverContent
        align="start"
        :side-offset="4"
        class="w-(--reka-popover-trigger-width) min-w-44 p-1.5"
      >
        <div class="flex flex-row flex-wrap items-center gap-1.5">
          <FilterTag
            v-for="tag in tags"
            :key="`${tag.categoryKey}:${tag.value}`"
            :label="tag.label"
            :count="tag.count"
            :tone="tag.tone"
            :icon="tag.icon"
            @remove="toggle(tag.categoryKey, tag.value)"
          />
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
