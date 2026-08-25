<script setup lang="ts">
import { computed, ref, type HTMLAttributes } from 'vue'
import type { TooltipContentProps } from 'reka-ui'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'
import { cn } from '@/lib/utils'

interface Props {
  title: string
  as?: string
  side?: TooltipContentProps['side']
  class?: HTMLAttributes['class']
  /** Clamp to this many lines instead of one. */
  lines?: 2 | 3
}

const props = defineProps<Props>()

// Spelled out so Tailwind sees the class names in the source.
const CLAMP = { 2: 'line-clamp-2', 3: 'line-clamp-3' } as const

const overflowClass = computed(() => (props.lines ? CLAMP[props.lines] : 'truncate'))

const textRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(textRef, () => props.title, props.lines ? 'y' : 'x')
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <component :is="props.as ?? 'p'" ref="textRef" :class="cn(overflowClass, props.class)">
        {{ props.title }}
      </component>
    </TooltipTrigger>
    <TooltipContent v-if="isTruncated" :title="props.title" :side="props.side" />
  </Tooltip>
</template>
