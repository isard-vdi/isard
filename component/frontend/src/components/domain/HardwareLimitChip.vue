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

// Marks a field the API already adjusted. Only the value the user asked for is
// shown; the one that was kept is right above, in the control itself.

const props = defineProps<{
  limited?: LimitedHardwareValue | null
}>()

const { t } = useI18n()

const oldValue = computed(() => formatLimitedValue(props.limited?.old_value))
const newValue = computed(() => formatLimitedValue(props.limited?.new_value))
const removed = computed(() => !!props.limited && isLimitedRemoval(props.limited))

const label = computed(() => {
  if (!props.limited) return ''
  if (!removed.value) {
    return t('components.domain.hardware.limited.chip.replaced', { old_value: oldValue.value })
  }
  const count = limitedValueCount(props.limited.old_value)
  return count > 1
    ? t('components.domain.hardware.limited.chip.removed-count', { count })
    : t('components.domain.hardware.limited.chip.removed', { old_value: oldValue.value })
})

const detail = computed(() => {
  if (!props.limited) return ''
  return removed.value
    ? t('components.domain.hardware.limited.detail.removed', { old_value: oldValue.value })
    : t('components.domain.hardware.limited.detail.replaced', {
        old_value: oldValue.value,
        new_value: newValue.value
      })
})
</script>

<template>
  <Tooltip v-if="limited">
    <!-- `w-fit!`: Field forces `w-full` on each of its direct children. -->
    <TooltipTrigger as-child>
      <span
        class="inline-flex w-fit! max-w-full items-center gap-1 rounded-md border border-warning-200 bg-warning-25 px-2 py-1 text-xs font-medium text-warning-800"
      >
        <Icon name="alert-triangle" size="xs" stroke-color="warning-800" aria-hidden="true" />
        <span class="truncate">{{ label }}</span>
      </span>
    </TooltipTrigger>
    <TooltipContent
      :title="t('components.domain.hardware.limited.warning.title')"
      :subtitle="detail"
      side="top"
    />
  </Tooltip>
</template>
