<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { overlayIconButtonClass } from '..'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const { t } = useI18n()

interface Props {
  icon: string
  // i18n key for the tooltip and, by default, the label revealed when active.
  title: string
  active?: boolean
  // i18n key for the active label when it differs from the tooltip (e.g. bastion).
  activeLabel?: string
  // i18n key; only set when the icon needs an explicit accessible name.
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  active: false,
  activeLabel: undefined,
  ariaLabel: undefined
})

defineEmits<{ click: [] }>()
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        hierarchy="link-gray"
        size="sm"
        :class="overlayIconButtonClass(props.active)"
        :icon="props.icon"
        icon-stroke-color="base-white"
        :aria-label="props.ariaLabel ? t(props.ariaLabel) : undefined"
        @click="$emit('click')"
      >
        <span v-if="props.active">{{ t(props.activeLabel ?? props.title) }}</span>
      </Button>
    </TooltipTrigger>
    <TooltipContent :title="t(props.title)" />
  </Tooltip>
</template>
