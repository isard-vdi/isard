<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { cn } from '@/lib/utils'

import type { Viewer } from '.'

import { Button } from '@/components/ui/button'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const { t } = useI18n()

interface Props {
  viewer: Viewer
  tooltipDismissed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  tooltipDismissed: false
})

const emit = defineEmits<{
  select: []
  dismissTooltip: []
}>()

const tooltipOpen = ref(false)

const handleDismiss = () => {
  tooltipOpen.value = false
  emit('dismissTooltip')
}
</script>

<template>
  <DropdownMenuItem
    :class="{ 'cursor-default data-[highlighted]:[&_button]:no-underline': props.viewer.loading }"
    @click="(!props.viewer.loading || props.viewer.status) && emit('select')"
  >
    <Tooltip
      :disabled="props.tooltipDismissed && !props.viewer.status"
      :open="tooltipOpen"
      @update:open="tooltipOpen = $event"
    >
      <TooltipTrigger as-child>
        <Button
          class="relative isolate mr-2 w-full justify-start overflow-hidden"
          hierarchy="link-gray"
          :icon="
            props.viewer.tone === 'error'
              ? 'alert-circle'
              : props.viewer.tone === 'warn'
                ? 'alert-triangle'
                : props.viewer.loading
                  ? 'loading-02'
                  : ''
          "
          icon-size="md"
          :icon-class="
            cn(
              'relative z-10',
              props.viewer.loading &&
                props.viewer.tone !== 'error' &&
                props.viewer.tone !== 'warn' &&
                'motion-safe:animate-[spin_2s_linear_infinite]'
            )
          "
          :disabled="props.viewer.loading && !props.viewer.status"
          :aria-disabled="props.viewer.loading ? 'true' : undefined"
        >
          <span
            v-if="props.viewer.progress !== undefined"
            class="viewer-progress"
            :class="`viewer-progress--${props.viewer.tone || 'wait'}`"
            :style="{ width: props.viewer.progress + '%' }"
            role="progressbar"
            :aria-valuenow="props.viewer.progress"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuetext="props.viewer.status"
            :aria-label="props.viewer.status"
          />
          <span class="relative z-10">{{ t(`viewers.${props.viewer.id}`) }}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent v-if="props.viewer.status" :title="props.viewer.status" side="left" />
      <TooltipContent
        v-else
        :title="t(`viewers.tooltip.${props.viewer.id}.title`)"
        :subtitle="t(`viewers.tooltip.${props.viewer.id}.description`)"
        :dismiss-label="t('viewers.tooltip-dismiss')"
        side="left"
        @dismiss="handleDismiss"
      />
    </Tooltip>
  </DropdownMenuItem>
</template>

<style scoped>
/* Same left-to-right readiness fill as the main viewer button. */
.viewer-progress {
  position: absolute;
  inset: 0 auto 0 0;
  z-index: 0;
  pointer-events: none;
  border-radius: inherit;
  transition: width 0.3s ease;
}
.viewer-progress--wait,
.viewer-progress--info {
  background-color: rgba(56, 189, 248, 0.4);
}
.viewer-progress--warn {
  background-color: rgba(251, 191, 36, 0.45);
}
.viewer-progress--error {
  background-color: rgba(248, 113, 113, 0.42);
}
</style>
