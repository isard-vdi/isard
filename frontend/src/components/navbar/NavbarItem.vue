<script setup lang="ts">
import { type HTMLAttributes } from 'vue'
import { Primitive, type PrimitiveProps } from 'radix-vue'
import { cn } from '@/lib/utils'
import Icon from '../icon/Icon.vue'
import { navbarItemVariants } from '.'

interface Props extends PrimitiveProps {
  icon: string
  label: string
  current?: boolean
  collapsed?: boolean
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
    :class="cn(navbarItemVariants({ current, collapsed }), props.class)"
  >
    <Icon :name="props.icon" class="w-[24px] h-[24px] fill-gray-warm-500" />
    <p v-if="!collapsed" class="leading-[24px] text-[16px]">
      {{ props.label }}
    </p>
  </Primitive>
</template>
