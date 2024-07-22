<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { Primitive, type PrimitiveProps } from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends PrimitiveProps {
  name: string
  alt?: string
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'img'
})

const url = computed(() => {
  return new URL(`../../assets/icons/${props.name}.svg`, import.meta.url).href
})
</script>

<template>
  <Primitive
    :src="url"
    :alt="alt || props.name + ' icon'"
    :as="as"
    :as-child="asChild"
    :class="cn('', props.class)"
  ></Primitive>
</template>
