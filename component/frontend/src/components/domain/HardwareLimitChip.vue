<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  formatLimitedValue,
  isLimitedRemoval,
  limitedValueCount,
  type LimitedHardwareValue
} from '@/lib/hardwareLimits'

// Marks a hardware field the API already adjusted.

const props = defineProps<{
  limited?: LimitedHardwareValue | null
}>()

const { t } = useI18n()

const title = computed(() => t('components.domain.hardware.limited.warning.title'))

const detail = computed(() => {
  if (!props.limited) return ''

  const oldValue = formatLimitedValue(props.limited.old_value)
  if (!isLimitedRemoval(props.limited)) {
    return t('components.domain.hardware.limited.detail.replaced', {
      old_value: oldValue,
      new_value: formatLimitedValue(props.limited.new_value)
    })
  }

  const count = limitedValueCount(props.limited.old_value)
  return count > 1
    ? t('components.domain.hardware.limited.detail.removed-count', { count, old_value: oldValue })
    : t('components.domain.hardware.limited.detail.removed', { old_value: oldValue })
})
</script>

<template>
  <Tooltip v-if="limited">
    <TooltipTrigger as-child>
      <button
        type="button"
        :aria-label="title"
        class="inline-flex shrink-0 cursor-default! items-center rounded-md border border-warning-200 bg-warning-25 p-1 text-warning-800 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <Icon name="alert-triangle" size="xs" stroke-color="warning-800" aria-hidden="true" />
      </button>
    </TooltipTrigger>
    <TooltipContent :title="title" :subtitle="detail" side="top" />
  </Tooltip>
</template>
