<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListboxContent, ListboxFilter, ListboxItem, ListboxRoot, useFilter } from 'reka-ui'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'
import type { AllowedOption } from '.'

interface Props {
  options: AllowedOption[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false
})

const model = defineModel<string[]>({ required: true })

const { t } = useI18n()
const { contains } = useFilter({ sensitivity: 'base' })

const open = ref(false)
const search = ref('')

watch(open, (value) => {
  if (!value) search.value = ''
})

const filteredOptions = computed(() => {
  if (!search.value) return props.options
  return props.options.filter(
    (option) =>
      contains(option.label, search.value) ||
      (option.subLabel !== undefined && contains(option.subLabel, search.value))
  )
})

const count = computed(() => model.value.length)

const isSelected = (value: string) => model.value.includes(value)

const update = (value: unknown) => {
  model.value = Array.isArray(value)
    ? value.filter((id): id is string => typeof id === 'string')
    : []
}

const clear = () => {
  model.value = []
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        :disabled="props.disabled"
        :aria-label="
          count ? t('components.filters.toggle-active', { count }) : t('components.filters.toggle')
        "
        data-slot="group-filter-trigger"
        :class="
          cn(
            'inline-flex h-10 shrink-0 cursor-pointer flex-row items-center gap-1.5 rounded-md border bg-base-white px-3 text-sm font-semibold shadow-[0px_1px_2px_0px_rgba(16,24,40,0.05)]',
            'hover:bg-gray-warm-50 focus:outline-hidden focus-visible:ring-4 focus-visible:ring-brand',
            'disabled:cursor-not-allowed disabled:border-gray-warm-200 disabled:text-gray-warm-400 disabled:hover:bg-base-white',
            count ? 'border-brand-700 text-brand-700' : 'border-gray-warm-300 text-gray-warm-600'
          )
        "
      >
        <Icon name="filter-funnel-02" size="sm" stroke-color="" />
        <span
          v-if="count"
          class="rounded-[4px] bg-brand-100 px-1 text-xs tabular-nums"
          data-slot="group-filter-count"
        >
          {{ count }}
        </span>
        <Icon name="chevron-down" size="sm" stroke-color="" />
      </button>
    </PopoverTrigger>

    <PopoverContent align="end" class="w-64 p-1">
      <ListboxRoot :model-value="model" multiple highlight-on-hover @update:model-value="update">
        <div class="flex items-center gap-2 border-b border-gray-warm-200 px-2 py-1.5">
          <Icon name="search-md" size="sm" stroke-color="gray-warm-500" class="shrink-0" />
          <ListboxFilter
            v-model="search"
            auto-focus
            :placeholder="t('components.allowed-modal.search.group.placeholder')"
            class="w-full bg-transparent text-md text-gray-warm-900 outline-none placeholder:font-regular placeholder:text-gray-warm-500"
          />
        </div>
        <ListboxContent
          class="max-h-[min(50vh,18rem)] scroll-py-1 overflow-x-hidden overflow-y-auto p-1 text-md text-gray-warm-900"
          tabindex="0"
        >
          <p v-if="filteredOptions.length === 0" class="px-2 py-1.5 text-gray-warm-500">
            {{ t('components.allowed-modal.search.group.empty') }}
          </p>
          <ListboxItem
            v-for="option in filteredOptions"
            :key="option.value"
            :value="option.value"
            class="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 outline-hidden data-highlighted:bg-brand-100"
          >
            <span
              aria-hidden="true"
              :class="
                cn(
                  'flex size-4 shrink-0 items-center justify-center rounded-sm border',
                  isSelected(option.value)
                    ? 'border-brand-700 bg-brand-700'
                    : 'border-input bg-base-white'
                )
              "
            >
              <Icon
                v-if="isSelected(option.value)"
                name="check"
                size="xs"
                stroke-color="base-white"
              />
            </span>
            <span class="truncate">{{ option.label }}</span>
          </ListboxItem>
        </ListboxContent>
      </ListboxRoot>

      <div v-if="count" class="border-t border-gray-warm-200 p-1">
        <button
          type="button"
          class="flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-gray-warm-700 hover:bg-error-100 hover:text-error-800 focus:bg-error-100 focus:text-error-800 focus:outline-hidden"
          data-slot="group-filter-clear"
          @click="clear"
        >
          <Icon name="x-circle" size="sm" stroke-color="" />
          {{ t('components.filters.clear') }}
        </button>
      </div>
    </PopoverContent>
  </Popover>
</template>
