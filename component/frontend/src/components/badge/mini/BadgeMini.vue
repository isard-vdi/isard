<script setup lang="ts">
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'
import { computed, type HTMLAttributes } from 'vue'

interface Variant {
  icon?: string
  class: HTMLAttributes['class']
  selectedClass?: HTMLAttributes['class']
}

const variants = {
  all: {
    icon: 'monitor-02',
    class: 'text-base-background bg-gray-warm-600'
  },
  persistent: {
    icon: 'browser',
    class: 'bg-secondary-3-400 text-secondary-3-600'
  },
  temporary: {
    icon: 'clock',
    class: 'bg-secondary-1-400 text-secondary-1-600'
  },
  deployment: {
    icon: 'layout-alt-04',
    class: 'bg-secondary-2-400 text-secondary-2-600'
  },
  'status-all': {
    class: 'text-base-background bg-gray-warm-600',
    selectedClass: 'bg-base-background text-gray-warm-600'
  },
  'status-started': {
    class: 'text-base-background bg-success-700',
    selectedClass: 'bg-base-background text-success-800'
  },
  'status-stopped': {
    class: 'text-base-background bg-error-600',
    selectedClass: 'bg-base-background text-error-700'
  }
} satisfies Record<string, Variant>

const props = withDefaults(
  defineProps<{
    name: keyof typeof variants
    value: string | number
    selected?: boolean
    class?: string
  }>(),
  { selected: false }
)

const variant = computed<Variant>(() => variants[props.name] ?? variants.all)
const style = computed(() =>
  props.selected
    ? (variant.value.selectedClass ?? 'bg-base-background text-gray-warm-600')
    : variant.value.class
)
const geometry = computed(() =>
  variant.value.icon ? '' : 'px-1.5 py-0.5 min-w-6 justify-center text-sm'
)
</script>

<template>
  <div
    :class="
      cn(
        `
        gap-1 px-1.75 py-1
        inline-flex items-center rounded-[6px]
        font-semibold font-medium text-md
        transition-colors focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2
        shadow-2xs drop-shadow-sm 
        `,
        geometry,
        style,
        props.class
      )
    "
  >
    <Icon v-if="variant.icon" :name="variant.icon" stroke-color="" />
    <span>{{ props.value }}</span>
  </div>
</template>
