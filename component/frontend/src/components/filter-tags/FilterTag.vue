<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'

import { filterToneStyle, type FilterTone } from '.'

interface Props {
  label: string
  count?: number
  tone?: FilterTone
  icon?: string
}

const props = defineProps<Props>()

defineEmits<{ remove: [] }>()

const { t } = useI18n()
</script>

<template>
  <span
    :class="
      cn(
        'inline-flex h-7 max-w-full shrink-0 items-center gap-1 rounded-[6px] pr-1 text-sm font-medium',
        props.icon ? 'pl-1.5' : 'pl-2',
        filterToneStyle(props.tone).fill
      )
    "
  >
    <!-- Inherits the tag's text colour, the one picked to read on its fill. -->
    <Icon
      v-if="props.icon"
      :name="props.icon"
      size="sm"
      stroke-color=""
      aria-hidden="true"
      class="shrink-0"
    />
    <span class="truncate">{{ props.label }}</span>
    <!-- How much of the list the filter leaves: the operator reads it here
         rather than opening the menu again. Lightened rather than dimmed, so the
         number keeps the contrast the label has. -->
    <span
      v-if="props.count !== undefined"
      data-filter-tag-count
      :class="
        cn(
          'shrink-0 rounded-[4px] px-1 text-xs font-semibold tabular-nums',
          filterToneStyle(props.tone).count
        )
      "
    >
      {{ props.count }}
    </span>
    <button
      type="button"
      class="flex shrink-0 items-center justify-center rounded-xs p-0.5 text-current hover:bg-error-100 hover:text-error-800 focus:bg-error-100 focus:text-error-800 focus:outline-none"
      :aria-label="t('components.filters.remove', { name: props.label })"
      @click="$emit('remove')"
    >
      <Icon name="x-close" size="sm" stroke-color="" aria-hidden="true" />
    </button>
  </span>
</template>
