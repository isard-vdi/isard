<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import type { SpinnerVariants } from '.'
import { cn } from '@/lib/utils'
import { spinnerVariants } from '.'
import SpinnerIcon from '@/assets/img/ui/spinner.svg?component'

interface Props {
  size?: SpinnerVariants['size']
  color?: SpinnerVariants['color']
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  color: 'green',
  class: undefined
})
</script>

<template>
  <SpinnerIcon
    role="status"
    aria-label="Loading"
    :class="cn(spinnerVariants({ size, color }), props.class)"
  />
</template>
