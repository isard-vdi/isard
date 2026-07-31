<script setup lang="ts">
import {
  ListboxContent,
  ListboxFilter,
  ListboxItem,
  ListboxItemIndicator,
  ListboxRoot,
  useFilter
} from 'reka-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { selectTriggerVariants } from '@/components/ui/select'
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'

// https://www.figma.com/design/B0Hv6jY90m5K6AtGwACAGo/ISARD-Design-system-Cliente--Copy-?node-id=3281-377673&t=K43HTMUALe5MqFog-4

interface Tag {
  value: string
  label: string
}

interface Props {
  modelValue?: string[]
  tags: Tag[]
  placeholder?: string
  disabled?: boolean
  invalid?: boolean
  previewCount?: number
  maxResults?: number
  maxVisibleTags?: number
  // wrap: chips wrap and overflow collapses into "+N". scroll: single scrollable row.
  tagsDisplay?: 'wrap' | 'scroll'
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  tags: () => [] as Tag[],
  placeholder: '',
  disabled: false,
  invalid: false,
  previewCount: 10,
  maxResults: 20,
  maxVisibleTags: 3,
  tagsDisplay: 'wrap'
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const { t } = useI18n()

const open = ref(false)
const searchTerm = ref('')

watch(open, (isOpen) => {
  if (!isOpen) searchTerm.value = ''
})

const { contains } = useFilter({ sensitivity: 'base' })

const selectedValues = computed(() => new Set(props.modelValue))

const selectedTags = computed(() =>
  props.modelValue
    .map((value) => props.tags.find((tag) => tag.value === value))
    .filter((tag): tag is Tag => Boolean(tag))
)

const isSearching = computed(() => searchTerm.value.trim() !== '')

const filteredTags = computed(() =>
  isSearching.value ? props.tags.filter((tag) => contains(tag.label, searchTerm.value)) : props.tags
)

// Pinned to the top so a capped list can't hide selected items with no way to unselect.
const selectedMatches = computed(() =>
  filteredTags.value.filter((tag) => selectedValues.value.has(tag.value))
)
const unselectedMatches = computed(() =>
  filteredTags.value.filter((tag) => !selectedValues.value.has(tag.value))
)

const resultLimit = computed(() => (isSearching.value ? props.maxResults : props.previewCount))

const visibleTags = computed(() => {
  const room = Math.max(0, resultLimit.value - selectedMatches.value.length)
  return [...selectedMatches.value, ...unselectedMatches.value.slice(0, room)]
})

const hiddenResultsCount = computed(() => filteredTags.value.length - visibleTags.value.length)

const visibleChips = computed(() =>
  props.tagsDisplay === 'scroll'
    ? selectedTags.value
    : selectedTags.value.slice(0, props.maxVisibleTags)
)
const hiddenChipsCount = computed(() => selectedTags.value.length - visibleChips.value.length)

const chipsRow = ref<HTMLElement | null>(null)
const hasOverflow = ref(false)

function measureOverflow() {
  const row = chipsRow.value
  hasOverflow.value = row ? row.scrollWidth > row.clientWidth : false
}

// Observer: control resized.
useResizeObserver(chipsRow, measureOverflow)
// Watcher: chips changed, which does not resize the row.
watch(
  [selectedTags, () => props.tagsDisplay],
  () => {
    nextTick(measureOverflow)
  },
  { immediate: true }
)

const scrollbarVisible = computed(() => props.tagsDisplay === 'scroll' && hasOverflow.value)

function removeTag(value: string) {
  emit(
    'update:modelValue',
    props.modelValue.filter((selected) => selected !== value)
  )
}
</script>

<template>
  <Popover v-model:open="open">
    <ListboxRoot
      :model-value="props.modelValue"
      highlight-on-hover
      multiple
      @update:model-value="emit('update:modelValue', $event)"
    >
      <PopoverTrigger as-child>
        <div
          role="combobox"
          :aria-expanded="open"
          :tabindex="props.disabled ? -1 : 0"
          :class="
            cn(
              selectTriggerVariants({ hierarchy: props.invalid ? 'destructive' : 'primary' }),
              'h-auto gap-2 cursor-pointer',
              scrollbarVisible ? 'min-h-12' : 'min-h-10',
              props.disabled && 'cursor-not-allowed opacity-50 pointer-events-none'
            )
          "
          @keydown.enter.prevent="open = !open"
          @keydown.space.prevent="open = !open"
        >
          <span
            v-if="selectedTags.length === 0"
            class="flex-1 min-w-0 text-left text-gray-warm-500 font-regular"
          >
            {{ props.placeholder }}
          </span>
          <div
            v-else
            ref="chipsRow"
            :class="
              cn(
                'flex-1 min-w-0 flex items-center gap-1.5',
                // scrollbar-width: index.css only styles ::-webkit-scrollbar, ignored by Firefox.
                props.tagsDisplay === 'wrap'
                  ? 'flex-wrap'
                  : 'flex-nowrap overflow-x-auto [scrollbar-width:thin]',
                scrollbarVisible && 'pb-3'
              )
            "
          >
            <span
              v-for="tag in visibleChips"
              :key="tag.value"
              class="flex shrink-0 items-center gap-1 max-w-[160px] h-6 pl-2 pr-1 rounded-md bg-brand-100 text-sm text-gray-warm-900"
            >
              <span class="truncate">{{ tag.label }}</span>
              <button
                type="button"
                class="shrink-0 flex items-center justify-center rounded-xs hover:bg-brand-200"
                :aria-label="t('components.searchable-tags.remove', { name: tag.label })"
                @click.stop="removeTag(tag.value)"
              >
                <Icon name="x-close" size="sm" stroke-color="gray-warm-500" />
              </button>
            </span>
            <span v-if="hiddenChipsCount > 0" class="shrink-0 text-sm text-gray-warm-500">
              +{{ hiddenChipsCount }}
            </span>
          </div>
          <Icon
            name="chevron-down"
            stroke-color="gray-warm-500"
            class="shrink-0 pointer-events-none"
          />
        </div>
      </PopoverTrigger>

      <PopoverContent class="p-1 w-(--reka-popper-anchor-width) border-brand-600">
        <div class="flex items-center gap-2 px-2 py-1.5 border-b border-gray-warm-200">
          <Icon name="search-md" size="sm" stroke-color="gray-warm-500" class="shrink-0" />
          <ListboxFilter
            v-model="searchTerm"
            auto-focus
            :placeholder="
              selectedTags.length === 0 ? t('components.searchable-tags.search-placeholder') : ''
            "
            class="w-full text-md text-gray-warm-900 outline-none bg-transparent placeholder:text-gray-warm-500 placeholder:font-regular"
          />
        </div>
        <ListboxContent
          class="max-h-[200px] scroll-py-1 overflow-x-hidden overflow-y-auto text-md text-gray-warm-900"
          tabindex="0"
        >
          <p v-if="filteredTags.length === 0" class="px-2 py-1.5 text-gray-warm-500">
            {{ t('components.searchable-tags.not-found') }}
          </p>
          <template v-else>
            <ListboxItem
              v-for="tag in visibleTags"
              :key="tag.value"
              class="data-[highlighted]:bg-brand-100 data-[highlighted]:text-accent-foreground relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
              :value="tag.value"
            >
              <span class="truncate">{{ tag.label }}</span>

              <ListboxItemIndicator class="ml-auto inline-flex items-center justify-center">
                <Icon name="check" stroke-color="brand-700" />
              </ListboxItemIndicator>
            </ListboxItem>
            <p v-if="hiddenResultsCount > 0" class="px-2 py-1.5 text-sm text-gray-warm-500">
              {{ t('components.searchable-tags.more-results', { count: hiddenResultsCount }) }}
            </p>
          </template>
        </ListboxContent>
      </PopoverContent>
    </ListboxRoot>
  </Popover>
</template>
