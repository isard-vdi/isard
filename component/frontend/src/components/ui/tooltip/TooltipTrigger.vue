<script setup lang="ts">
import type { TooltipTriggerProps } from 'reka-ui'
import { TooltipTrigger } from 'reka-ui'
import { provideTooltipTriggerTitle } from './context'

const props = defineProps<TooltipTriggerProps>()

provideTooltipTriggerTitle()
</script>

<template>
  <TooltipTrigger data-slot="tooltip-trigger" v-bind="props">
    <slot />
  </TooltipTrigger>
</template>
