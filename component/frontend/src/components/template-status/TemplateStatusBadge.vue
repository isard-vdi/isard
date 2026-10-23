<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import type { TemplateStatus } from './status'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    status: TemplateStatus
    // Off where the whole row already carries the same tooltip.
    tooltip?: boolean
  }>(),
  { tooltip: true }
)

const BADGE = {
  failed: {
    icon: 'info-circle',
    class: 'text-error-600',
    label: 'views.templates.table.failed-badge',
    message: 'views.templates.table.failed-message'
  },
  hidden: {
    icon: 'eye-off',
    class: 'text-gray-warm-600',
    label: 'views.templates.table.hidden-badge',
    message: 'views.templates.table.hidden-message'
  }
} as const
</script>

<template>
  <Tooltip :disabled="!props.tooltip">
    <TooltipTrigger as-child>
      <div
        :class="[
          'inline-flex items-center gap-1.5 font-semibold max-w-full w-max text-xs',
          BADGE[props.status].class
        ]"
      >
        <span aria-hidden="true" class="contents">
          <Icon
            :name="BADGE[props.status].icon"
            class="size-3.5 shrink-0"
            stroke-color="currentColor"
          />
        </span>
        <span class="truncate">{{ t(BADGE[props.status].label) }}</span>
      </div>
    </TooltipTrigger>
    <TooltipContent :title="t(BADGE[props.status].message)" />
  </Tooltip>
  <span class="sr-only">{{ t(BADGE[props.status].message) }}</span>
</template>
