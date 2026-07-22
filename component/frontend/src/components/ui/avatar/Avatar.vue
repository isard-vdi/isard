<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import type { AvatarVariants } from '.'
import { AvatarRoot } from 'reka-ui'
import { cn } from '@/lib/utils'
import { avatarVariant } from '.'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    size?: AvatarVariants['size']
    shape?: AvatarVariants['shape']
  }>(),
  {
    size: 'sm',
    shape: 'circle'
  }
)
</script>

<template>
  <div class="flex items-center space-x-2">
    <AvatarRoot :class="cn(avatarVariant({ size, shape }), props.class)">
      <slot />
    </AvatarRoot>
  </div>
</template>
