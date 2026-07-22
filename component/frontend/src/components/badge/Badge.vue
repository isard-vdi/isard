<script setup lang="ts">
import { cn } from '@/lib/utils'
import { computed, type HTMLAttributes } from 'vue'
import { Icon, type IconVariants } from '@/components/icon'

interface Color {
  class: HTMLAttributes['class']
  icon: string
}

const colors = {
  blue: {
    class: 'bg-info-100 text-info-800',
    icon: 'info-600'
  },
  red: {
    class: 'bg-error-100 text-error-800 border-error-200',
    icon: 'error-600'
  },
  lightred: {
    class: 'bg-error-50 text-error-800 border-error-200',
    icon: 'error-500'
  },
  violet: {
    class: 'bg-badges-violet-200 text-badges-violet-700',
    icon: ''
  },
  indigo: {
    class: 'bg-badges-indigo-200 text-badges-indigo-700',
    icon: ''
  },
  gray: {
    class: 'bg-gray-warm-100 text-gray-warm-800',
    icon: 'gray-600'
  },
  lightyellow: {
    class: 'bg-warning-50 text-warning-800 border-warning-200',
    icon: 'warning-500'
  },
  green: {
    class: 'bg-success-100 text-success-800',
    icon: 'success-600'
  },
  lightgreen: {
    class: 'bg-success-50 text-success-800 border-success-200',
    icon: 'success-500'
  },
  'viewer-blue': {
    class: 'bg-badges-viewer-blue text-brand-900',
    icon: ''
  },
  'viewer-violet': {
    class: 'bg-badges-viewer-violet text-badges-violet-900',
    icon: ''
  }
} satisfies Record<string, Color>

const shapes = {
  square: 'rounded-[6px] shadow-2xs drop-shadow-sm',
  pill: 'rounded-full border-2'
} satisfies Record<string, string>

interface Size {
  badge: string
  icon: NonNullable<IconVariants['size']>
  gap: string
}

const sizes = {
  sm: {
    badge: 'px-2 py-0.5 text-sm font-medium',
    icon: 'xs'
  },
  md: {
    badge: 'px-2 py-0.5 text-lg font-medium',
    icon: 'sm',
    gap: 'gap-1'
  },
  lg: {
    badge: 'px-3 py-0.5 text-xl font-medium',
    icon: 'md',
    gap: 'gap-1.5'
  }
} satisfies Record<string, Size>

const props = withDefaults(
  defineProps<{
    color: keyof typeof colors
    content: string
    shape: keyof typeof shapes
    icon?: string
    size?: keyof typeof sizes
    class?: HTMLAttributes['class']
    border?: boolean
  }>(),
  {
    border: false,
    size: 'md'
  }
)

const color = computed(() => colors[props.color] ?? colors.gray)
const size = computed(() => sizes[props.size] ?? sizes.md)
const shape = computed(() => shapes[props.shape] ?? shapes.square)
</script>

<template>
  <div
    :class="
      cn(
        `
      inline-flex
      items-center
      font-semibold
      transition-colors
      focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2
      `,
        size.badge,
        color.class,
        props.icon ? size.gap : '',
        shape,
        props.class
      )
    "
  >
    <Icon v-if="props.icon" :name="props.icon" :size="size.icon" :stroke-color="color.icon" />
    <span>{{ props.content }}</span>
  </div>
</template>
