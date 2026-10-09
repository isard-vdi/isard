<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { BAR_BUTTON, MAX_PINNED } from '../constants'

interface Props {
  pinned: boolean
  pinFull: boolean
  /** Index of the open desktop among the steps, -1 when it is not one of them. */
  position: number
  total: number
  /** The arrow keys step too, while the desktop does not have the keyboard. */
  shortcuts: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{ pin: []; step: [offset: number] }>()

const { t } = useI18n()

const pinLabel = computed(() =>
  props.pinned
    ? t('views.deployment-videowall.viewer.pinned.unpin')
    : props.pinFull
      ? t('views.deployment-videowall.viewer.pinned.limit', { max: MAX_PINNED })
      : t('views.deployment-videowall.viewer.pinned.pin')
)

const stepControls = computed(() => ({
  previous: {
    icon: 'chevron-left',
    label: t('views.deployment-videowall.viewer.previous'),
    disabled: props.position <= 0,
    offset: -1,
    key: 'ArrowLeft',
    symbol: '←'
  },
  next: {
    icon: 'chevron-right',
    label: t('views.deployment-videowall.viewer.next'),
    disabled: props.position < 0 || props.position >= props.total - 1,
    offset: 1,
    key: 'ArrowRight',
    symbol: '→'
  }
}))
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <!-- aria-disabled keeps the tooltip, which says why, reachable. -->
      <button
        type="button"
        :class="cn(BAR_BUTTON, props.pinned && 'bg-gray-warm-100', props.pinFull && 'opacity-40')"
        :aria-label="pinLabel"
        :aria-pressed="props.pinned"
        :aria-disabled="props.pinFull"
        @click="emit('pin')"
      >
        <Icon
          name="pin-02"
          size="lg"
          :stroke-color="props.pinned ? 'brand-600' : 'gray-warm-600'"
        />
      </button>
    </TooltipTrigger>
    <TooltipContent :title="pinLabel" />
  </Tooltip>
  <div class="mx-2 h-6 w-px bg-gray-warm-200" />
  <div class="flex items-center gap-1">
    <template v-for="(control, key) in stepControls" :key="key">
      <span
        v-if="key === 'next' && props.position >= 0"
        class="min-w-16 text-center text-sm font-medium text-gray-warm-600 tabular-nums"
      >
        {{
          t('views.deployment-videowall.viewer.position', {
            current: props.position + 1,
            total: props.total
          })
        }}
      </span>
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            type="button"
            :class="BAR_BUTTON"
            :disabled="control.disabled"
            :aria-label="control.label"
            :aria-keyshortcuts="props.shortcuts ? control.key : undefined"
            @click="emit('step', control.offset)"
          >
            <Icon :name="control.icon" size="lg" stroke-color="gray-warm-600" />
          </button>
        </TooltipTrigger>
        <TooltipContent
          :title="props.shortcuts ? `${control.label} (${control.symbol})` : control.label"
        />
      </Tooltip>
    </template>
  </div>
</template>
