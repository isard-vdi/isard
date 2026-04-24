<script setup lang="ts">
import { defineAsyncComponent, shallowRef, watch, type HTMLAttributes } from 'vue'
import { type IconVariants, iconVariants } from '.'
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

function getIcon(name: string) {
  return defineAsyncComponent(async () => {
    try {
      return (await import(`@/assets/icons/${name}.svg?component`)).default
    } catch (e: unknown) {
      const msg = `Failed load icon '${name}': ` + (e instanceof Error ? e.message : String(e))
      console.error(msg)
    }

    try {
      console.warn('using fallback icon')
      // @ts-expect-error - TS doesn't like the ?component part, but it exists.
      return (await import('@/assets/icons/face-smile.svg?component')).default
    } catch (e) {
      console.error(e)
      return
    }
  })
}

const icon = shallowRef(getIcon(props.name))
watch(
  () => props.name,
  (newName) => (icon.value = getIcon(newName))
)
</script>

<template>
  <component
    :is="icon"
    v-if="icon"
    :alt="props.alt ?? props.name + ' icon'"
    :class="cn(iconVariants({ size }), props.class)"
    :style="{
      fill: props.fillColor ? `var(--${props.fillColor})` : '',
      color: props.strokeColor ? `var(--${props.strokeColor})` : ''
    }"
  />
</template>
