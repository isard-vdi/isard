<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import { Avatar, AvatarImage, AvatarFallback, type AvatarVariants } from '@/components/ui/avatar'
import { type HTMLAttributes } from 'vue'

const sizes: Record<
  NonNullable<AvatarVariants['size']>,
  { base: string; name: string; sub: string }
> = {
  xs: {
    base: 'gap-2',
    name: 'text-xs font-medium',
    sub: 'text-xs'
  },
  sm: {
    base: 'gap-2.5',
    name: 'text-sm font-medium',
    sub: 'text-xs'
  },
  md: {
    base: 'gap-3',
    name: 'text-sm font-semibold',
    sub: 'text-sm'
  },
  lg: {
    base: 'gap-3',
    name: 'text-md font-semibold',
    sub: 'text-md'
  },
  xl: {
    base: 'gap-4',
    name: 'text-lg font-semibold',
    sub: 'text-md'
  },
  '2xl': {
    base: 'gap-4',
    name: 'text-xl font-semibold',
    sub: 'text-lg'
  }
}

interface Props {
  src: string
  size?: NonNullable<AvatarVariants['size']>
  shape?: 'square' | 'circle'
  fallback?: string
  name: string
  sub?: string
  nameClass?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  size: 'sm',
  shape: 'circle',
  fallback: undefined,
  sub: undefined
})

const fallback = computed(() => {
  if (props.fallback) {
    return props.fallback
  }

  return props.name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
})
</script>

<template>
  <div :class="cn('flex items-center', sizes[props.size].base)">
    <Avatar :size="props.size" :shape="props.shape">
      <AvatarImage :src="props.src" :alt="props.name" />
      <AvatarFallback>{{ fallback }}</AvatarFallback>
    </Avatar>
    <div>
      <span :class="cn('block', sizes[props.size].name, props.nameClass)">{{ props.name }}</span>
      <span :class="cn('block', sizes[props.size].sub)">{{ props.sub }}</span>
    </div>
  </div>
</template>
