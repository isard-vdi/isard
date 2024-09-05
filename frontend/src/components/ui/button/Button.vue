<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { Primitive, type PrimitiveProps } from 'radix-vue'
import { type ButtonVariants, buttonVariants } from '.'
import { cn } from '@/lib/utils'
import { Icon } from '@/components/icon'

interface Props extends PrimitiveProps {
  hierarchy?: ButtonVariants['hierarchy']
  size?: ButtonVariants['size']
  icon?: string
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button'
})
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    :class="cn(buttonVariants({ hierarchy, size }), props.class)"
  >
    <Icon v-if="props.icon" :name="props.icon" class="pr-3" />
    <slot />
  </Primitive>
</template>
