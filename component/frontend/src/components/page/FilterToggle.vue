<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWindowSize } from '@vueuse/core'

import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const props = withDefaults(
  defineProps<{
    activeCount?: number
  }>(),
  { activeCount: 0 }
)

const open = defineModel<boolean>({ default: false })

const { t } = useI18n()
const { width } = useWindowSize()

// Below `sm` the button drops its label, so a tooltip takes over
const isSmallScreen = computed(() => width.value < 640)

const label = computed(() =>
  props.activeCount
    ? t('components.filters.toggle-active', { count: props.activeCount })
    : t('components.filters.toggle')
)
</script>

<template>
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger as-child>
        <Button
          hierarchy="secondary-gray"
          icon="filter-funnel-02"
          :aria-label="label"
          :class="cn('relative shrink-0 max-sm:px-[10px]', open && 'bg-gray-warm-50')"
          @click="open = !open"
        >
          <span class="max-sm:hidden">{{ t('components.filters.toggle') }}</span>
          <!-- Stays visible with the panel collapsed, and on small screens
               where the label is hidden. -->
          <span
            v-if="props.activeCount"
            aria-hidden="true"
            class="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-brand-600 ring-2 ring-base-background"
          />
        </Button>
      </TooltipTrigger>
      <TooltipContent v-if="isSmallScreen || props.activeCount" :title="label" side="top" />
    </Tooltip>
  </TooltipProvider>
</template>
