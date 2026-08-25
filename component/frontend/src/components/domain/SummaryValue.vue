<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '../icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

const props = withDefaults(
  defineProps<{
    value: string
    icon?: string
    label?: string
    changed?: boolean
    truncate?: boolean
  }>(),
  {
    icon: undefined,
    label: undefined,
    changed: false,
    truncate: false
  }
)

const { t } = useI18n()

const valueRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(valueRef, () => props.value)
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <span
        :class="[
          'flex items-center gap-1.5 [&_svg]:shrink-0',
          changed ? 'rounded-md bg-secondary-3-100 px-2 py-1' : ''
        ]"
      >
        <Icon
          v-if="icon"
          aria-hidden="true"
          :name="icon"
          size="sm"
          stroke-color=""
          :class="changed ? 'text-brand-700' : 'text-gray-warm-500'"
        />
        <span
          v-if="label"
          :class="[
            'text-xs font-semibold uppercase tracking-wide shrink-0',
            changed ? 'text-brand-700/70' : 'text-gray-warm-500'
          ]"
          >{{ label }}</span
        >
        <span
          ref="valueRef"
          :class="[
            'text-sm font-semibold',
            changed ? 'text-brand-700' : 'text-gray-warm-800',
            truncate ? 'max-w-40 truncate' : ''
          ]"
          >{{ value }}</span
        >
      </span>
    </TooltipTrigger>
    <TooltipContent
      v-if="isTruncated || changed"
      :title="isTruncated ? value : t('components.domain-summary.changed')"
      side="top"
    />
  </Tooltip>
</template>
