<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '../icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

/** How a field stands against the value the forms were seeded with. */
export type SummaryValueState = 'changed' | 'added' | 'removed'

const props = withDefaults(
  defineProps<{
    value: string
    icon?: string
    label?: string
    state?: SummaryValueState
    previous?: string | null
    truncate?: boolean
  }>(),
  {
    icon: undefined,
    label: undefined,
    state: undefined,
    previous: null,
    truncate: false
  }
)

const { t } = useI18n()

const valueRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(valueRef, () => props.value)

const tone = computed(() => {
  if (props.state === 'removed') {
    return {
      wrapper: '',
      icon: 'text-gray-warm-400',
      label: 'text-gray-warm-400',
      value: 'font-regular text-gray-warm-400 line-through'
    }
  }
  if (props.state) {
    return {
      wrapper: 'rounded-md bg-secondary-3-100 px-2 py-1',
      icon: 'text-brand-700',
      label: 'text-brand-700/70',
      value: 'font-semibold text-brand-700'
    }
  }
  return {
    wrapper: '',
    icon: 'text-gray-warm-500',
    label: 'text-gray-warm-500',
    value: 'font-semibold text-gray-warm-800'
  }
})

const stateLabel = computed(() =>
  props.state ? t(`components.domain-summary.${props.state}`) : undefined
)

const tooltipTitle = computed(() => stateLabel.value ?? props.value)

const tooltipSubtitle = computed(() => {
  const lines: string[] = []
  if (isTruncated.value && stateLabel.value) lines.push(props.value)
  if (props.previous) {
    lines.push(t('components.domain-summary.previous-value', { value: props.previous }))
  }
  return lines.length ? lines.join('\n') : undefined
})
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <span :class="['flex items-center gap-1.5 [&_svg]:shrink-0', tone.wrapper]">
        <Icon
          v-if="icon"
          aria-hidden="true"
          :name="icon"
          size="sm"
          stroke-color=""
          :class="tone.icon"
        />
        <span
          v-if="label"
          :class="['text-xs font-semibold uppercase tracking-wide shrink-0', tone.label]"
          >{{ label }}</span
        >
        <span
          ref="valueRef"
          :class="['text-sm', tone.value, truncate ? 'max-w-40 truncate' : '']"
          >{{ value }}</span
        >
      </span>
    </TooltipTrigger>
    <TooltipContent
      v-if="isTruncated || state"
      :title="tooltipTitle"
      :subtitle="tooltipSubtitle"
      class="whitespace-pre-line"
      side="top"
    />
  </Tooltip>
</template>
