<script setup lang="ts">
import { shallowRef, watch, type HTMLAttributes } from 'vue'
import { type IconVariants, iconVariants } from '.'
import { getIcon } from './icons'
import { cn } from '@/lib/utils'

export interface Props {
  name: string
  size?: IconVariants['size']
  alt?: string
  class?: HTMLAttributes['class']
  fillColor?: string
  strokeColor?: string
}

const props = withDefaults(defineProps<Props>(), {
  strokeColor: 'gray-warm-800'
})

const icon = shallowRef(getIcon(props.name))
watch(
  () => props.name,
  (newName) => (icon.value = getIcon(newName))
)
</script>

<template>
  <component
    :is="icon"
    :alt="props.alt ?? props.name + ' icon'"
    :class="cn(iconVariants({ size }), props.class)"
    :style="{
      fill: props.fillColor ? `var(--${props.fillColor})` : '',
      color: props.strokeColor ? `var(--${props.strokeColor})` : ''
    }"
  />
</template>
