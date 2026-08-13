<script setup lang="ts">
import { ref, type HTMLAttributes } from 'vue'
import type { TooltipContentProps } from 'reka-ui'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'
import { cn } from '@/lib/utils'

interface Props {
  title: string
  as?: string
  side?: TooltipContentProps['side']
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const textRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(textRef, () => props.title)
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <component :is="props.as ?? 'p'" ref="textRef" :class="cn('truncate', props.class)">
        {{ props.title }}
      </component>
    </TooltipTrigger>
    <TooltipContent v-if="isTruncated" :title="props.title" :side="props.side" />
  </Tooltip>
</template>
