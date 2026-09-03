<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ListboxContent,
  ListboxFilter,
  ListboxItem,
  ListboxItemIndicator,
  ListboxRoot,
  useFilter
} from 'reka-ui'
import { monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'
import { reorderWithEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/util/reorder-with-edge'
import { triggerPostMoveFlash } from '@atlaskit/pragmatic-drag-and-drop-flourish/trigger-post-move-flash'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { selectTriggerVariants } from '@/components/ui/select'
import { DraggableItem } from '@/components/drag-and-drop'
import { Icon } from '@/components/icon'
import { TruncatedText } from '@/components/truncated-text'
import { cn } from '@/lib/utils'

export interface NetworkOption {
  id: string
  name: string
}

interface Props {
  id?: string
  modelValue?: string[]
  options?: NetworkOption[]
  placeholder?: string
  disabled?: boolean
  invalid?: boolean
  /** Ids another part of the form depends on; flagged so removing one is deliberate. */
  requiredIds?: string[]
  /** Results shown in the picker before typing, and per search. */
  previewCount?: number
  maxResults?: number
}

const props = withDefaults(defineProps<Props>(), {
  id: undefined,
  modelValue: () => [],
  options: () => [],
  placeholder: '',
  disabled: false,
  invalid: false,
  requiredIds: () => [],
  previewCount: 10,
  maxResults: 20
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const { t } = useI18n()
const { contains } = useFilter({ sensitivity: 'base' })

const open = ref(false)
const searchTerm = ref('')

watch(open, (isOpen) => {
  if (!isOpen) searchTerm.value = ''
})

const nameOf = (id: string) => props.options.find((option) => option.id === id)?.name ?? id

// The selection is the ordered value: position N is the Nth interface of the domain.
const selected = computed(() => props.modelValue.map((id) => ({ id, name: nameOf(id) })))

const isSearching = computed(() => searchTerm.value.trim() !== '')

const filtered = computed(() =>
  isSearching.value
    ? props.options.filter((option) => contains(option.name, searchTerm.value))
    : props.options
)

// Selected first, so a capped list can never hide an item with no way to unpick it.
const visibleOptions = computed(() => {
  const picked = filtered.value.filter((option) => props.modelValue.includes(option.id))
  const rest = filtered.value.filter((option) => !props.modelValue.includes(option.id))
  const limit = isSearching.value ? props.maxResults : props.previewCount
  return [...picked, ...rest.slice(0, Math.max(0, limit - picked.length))]
})

const hiddenResultsCount = computed(() => filtered.value.length - visibleOptions.value.length)

const isRequired = (id: string) => props.requiredIds.includes(id)

// aria-label on the chip replaces its contents, so the flag has to be part of the name.
const chipLabel = (network: { id: string; name: string }, index: number) =>
  t(
    isRequired(network.id)
      ? 'components.domain.hardware.networks.chip-label-required'
      : 'components.domain.hardware.networks.chip-label',
    { name: network.name, position: index + 1 }
  )

// The listbox reports a set, so keep our own order and append whatever is new.
const handlePick = (next: unknown) => {
  const picked = (next ?? []) as string[]
  const kept = props.modelValue.filter((id) => picked.includes(id))
  const added = picked.filter((id) => !props.modelValue.includes(id))
  emit('update:modelValue', [...kept, ...added])
}

const remove = (id: string) => {
  emit(
    'update:modelValue',
    props.modelValue.filter((selectedId) => selectedId !== id)
  )
}

const move = async (from: number, to: number) => {
  if (props.disabled || to < 0 || to >= props.modelValue.length) return
  const next = [...props.modelValue]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  emit('update:modelValue', next)
  // The chip is re-rendered in its new slot, so put the focus back on it.
  await nextTick()
  chipOf(moved)?.focus()
  flash(moved)
}

const chipOf = (id: string): HTMLElement | null => {
  const element = listRef.value?.querySelector(`[data-item-id="${CSS.escape(id)}"]`)
  return element instanceof HTMLElement ? element : null
}

const flash = (id: string) => {
  const chip = chipOf(id)
  if (chip) triggerPostMoveFlash(chip)
}

const listRef = ref<HTMLElement | null>(null)

let cleanup: () => void = () => {
  /* noop — replaced on mount */
}

onMounted(() => {
  cleanup = monitorForElements({
    onDrop: ({ location, source }) => {
      const target = location.current.dropTargets[0]
      // Only reorder drops that start and land inside this list.
      if (!target || !listRef.value?.contains(target.element)) return
      if (!(source.element instanceof HTMLElement) || !listRef.value.contains(source.element))
        return

      const startIndex = source.data.index as number
      const indexOfTarget = target.data.index as number
      if (startIndex === indexOfTarget) return

      emit(
        'update:modelValue',
        reorderWithEdge({
          list: props.modelValue,
          startIndex,
          indexOfTarget,
          closestEdgeOfTarget: extractClosestEdge(target.data),
          axis: 'horizontal'
        })
      )
      flash((source.data.item as { value: string }).value)
    }
  })
})

onUnmounted(() => cleanup())
</script>

<template>
  <div class="flex flex-col gap-2">
    <Popover v-model:open="open">
      <ListboxRoot
        :model-value="props.modelValue"
        highlight-on-hover
        multiple
        @update:model-value="handlePick"
      >
        <PopoverTrigger as-child>
          <div
            :id="props.id"
            role="combobox"
            :aria-expanded="open"
            :aria-label="props.placeholder"
            :tabindex="props.disabled ? -1 : 0"
            :class="
              cn(
                selectTriggerVariants({ hierarchy: props.invalid ? 'destructive' : 'primary' }),
                'w-full sm:w-[260px] gap-2 cursor-pointer',
                props.disabled && 'cursor-not-allowed opacity-50 pointer-events-none'
              )
            "
            @keydown.enter.prevent="open = !open"
            @keydown.space.prevent="open = !open"
          >
            <Icon name="plus" size="sm" stroke-color="gray-warm-500" class="shrink-0" />
            <span class="flex-1 min-w-0 text-left text-gray-warm-500 font-regular truncate">
              {{ props.placeholder }}
            </span>
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
              :placeholder="t('components.searchable-tags.search-placeholder')"
              class="w-full text-md text-gray-warm-900 outline-none bg-transparent placeholder:text-gray-warm-500 placeholder:font-regular"
            />
          </div>
          <ListboxContent
            class="max-h-[200px] scroll-py-1 overflow-x-hidden overflow-y-auto text-md text-gray-warm-900"
            tabindex="0"
          >
            <p v-if="filtered.length === 0" class="px-2 py-1.5 text-gray-warm-500">
              {{ t('components.searchable-tags.not-found') }}
            </p>
            <template v-else>
              <ListboxItem
                v-for="option in visibleOptions"
                :key="option.id"
                class="data-[highlighted]:bg-brand-100 relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 outline-hidden select-none"
                :value="option.id"
              >
                <span class="truncate">{{ option.name }}</span>
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

    <div
      class="flex flex-col gap-2 min-h-14 p-2 rounded-md border border-dashed border-gray-warm-300 bg-gray-warm-50"
    >
      <ul ref="listRef" class="flex flex-wrap items-center gap-2 content-start">
        <li v-if="selected.length === 0" class="text-sm text-gray-warm-500 font-regular">
          {{ t('components.domain.hardware.networks.empty') }}
        </li>
        <li v-for="(network, index) in selected" :key="network.id" class="relative">
          <DraggableItem
            :item="{ value: network.id, label: network.name }"
            :index="index"
            orientation="horizontal"
            class="h-10 gap-2 py-0 px-2 rounded-md border-gray-warm-300 bg-base-white text-md leading-md text-gray-warm-900 font-medium focus:outline-none focus:border-gray-warm-700 focus:ring-3 focus:ring-brand"
            :tabindex="props.disabled ? -1 : 0"
            :aria-label="chipLabel(network, index)"
            @keydown.left.prevent="move(index, index - 1)"
            @keydown.right.prevent="move(index, index + 1)"
          >
            <template #default="{ item }">
              <Icon
                name="dots-grid-vertical"
                size="sm"
                stroke-color="gray-warm-400"
                class="shrink-0"
                aria-hidden="true"
              />
              <span class="shrink-0 text-gray-warm-500" aria-hidden="true">{{ index + 1 }}.</span>
              <TruncatedText as="span" :title="item.label" side="top" class="max-w-[180px]" />
              <span
                v-if="isRequired(item.value)"
                aria-hidden="true"
                class="shrink-0 px-1.5 rounded-full bg-warning-100 text-xs font-medium text-warning-800"
              >
                {{ t('components.domain.hardware.networks.required') }}
              </span>
              <button
                type="button"
                class="shrink-0 flex items-center justify-center rounded-xs p-0.5 hover:bg-error-50 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="props.disabled"
                :aria-label="t('components.domain.hardware.networks.remove', { name: item.label })"
                @click.stop="remove(item.value)"
              >
                <Icon name="x-close" size="sm" stroke-color="error-500" />
              </button>
            </template>
          </DraggableItem>
        </li>
      </ul>

      <p v-if="selected.length > 1" class="text-xs text-gray-warm-500">
        {{ t('components.domain.hardware.networks.order-hint') }}
      </p>
    </div>
  </div>
</template>
