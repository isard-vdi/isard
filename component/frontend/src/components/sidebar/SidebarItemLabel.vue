<script setup lang="ts">
import { ref, type HTMLAttributes } from 'vue'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

interface Props {
  label: string
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const labelRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(labelRef, () => props.label)
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <p ref="labelRef" :class="props.class">{{ props.label }}</p>
    </TooltipTrigger>
    <TooltipContent v-if="isTruncated" :title="props.label" side="right" />
  </Tooltip>
</template>
