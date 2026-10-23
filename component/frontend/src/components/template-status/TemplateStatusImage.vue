<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import DomainImage from '@/components/domain/DomainImage.vue'
import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import type { TemplateStatus } from './status'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    imageUrl: string
    status?: TemplateStatus
    // Off where the whole row already carries the same tooltip.
    tooltip?: boolean
  }>(),
  { status: undefined, tooltip: true }
)

const OVERLAY = {
  failed: {
    icon: 'alert-triangle',
    iconColor: 'error-700',
    class: 'bg-error-200/60 ring-error-600/20 shadow-error-700',
    message: 'views.templates.table.failed-message'
  },
  hidden: {
    icon: 'eye-off',
    iconColor: 'gray-warm-700',
    class: 'bg-gray-warm-200/60 ring-gray-warm-600/20 shadow-gray-warm-700',
    message: 'views.templates.table.hidden-message'
  }
} as const
</script>

<template>
  <div class="relative">
    <DomainImage
      :image-url="props.imageUrl"
      variant="compact"
      :class="[
        'w-48 h-16 shrink-0 rounded-l-2xl',
        {
          'grayscale opacity-40': props.status === 'failed',
          'opacity-60': props.status === 'hidden'
        }
      ]"
    >
      <slot />
    </DomainImage>

    <Tooltip v-if="props.status" :disabled="!props.tooltip">
      <TooltipTrigger as-child>
        <div
          aria-hidden="true"
          :class="[
            'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center p-1.5 rounded-full backdrop-blur-xs border-2 border-base-white ring-[3px] ring-offset-1 ring-offset-base-white/30 shadow-md',
            OVERLAY[props.status].class
          ]"
        >
          <Icon
            :name="OVERLAY[props.status].icon"
            size="xl"
            :stroke-color="OVERLAY[props.status].iconColor"
          />
        </div>
      </TooltipTrigger>
      <TooltipContent :title="t(OVERLAY[props.status].message)" />
    </Tooltip>
  </div>
</template>
