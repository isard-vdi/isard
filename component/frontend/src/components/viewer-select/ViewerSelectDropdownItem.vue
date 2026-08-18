<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

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
  <DropdownMenuItem>
    <Tooltip
      :disabled="props.tooltipDismissed"
      :open="tooltipOpen"
      @update:open="tooltipOpen = $event"
    >
      <TooltipTrigger as-child>
        <Button
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          :icon="props.viewer.loading ? 'loading-02' : ''"
          icon-size="md"
          icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
          :disabled="props.viewer.loading"
          @click="emit('select')"
        >
          {{ t(`viewers.${props.viewer.id}`) }}
        </Button>
      </TooltipTrigger>
      <TooltipContent
        :title="t(`viewers.tooltip.${props.viewer.id}.title`)"
        :subtitle="t(`viewers.tooltip.${props.viewer.id}.description`)"
        :dismiss-label="t('viewers.tooltip-dismiss')"
        side="left"
        @dismiss="handleDismiss"
      />
    </Tooltip>
  </DropdownMenuItem>
</template>
