<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { Separator, type SeparatorProps } from 'radix-vue'
import { cn } from '@/lib/utils'

const props = defineProps<SeparatorProps & { class?: HTMLAttributes['class']; label?: string }>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props

  return delegated
})
</script>

<template>
  <Separator
    v-bind="delegatedProps"
    :class="
      cn(
        'relative flex items-center',
        props.orientation === 'vertical' ? 'flex-col' : 'flex-row',
        props.class
      )
    "
  >
    <div
      :class="
        cn(
          'bg-gray-warm-200 flex-grow',
          props.orientation === 'vertical' ? 'w-px h-full' : 'h-px w-full'
        )
      "
    ></div>
    <span
      v-if="props.label"
      :class="
        cn(
          'text-xs text-muted-foreground bg-background px-2 z-10 whitespace-nowrap',
          props.orientation === 'vertical' ? 'py-1' : 'px-2'
        )
      "
    >
      {{ props.label }}
    </span>
    <div
      :class="
        cn(
          'bg-gray-warm-200 flex-grow',
          props.orientation === 'vertical' ? 'w-px h-full' : 'h-px w-full'
        )
      "
    ></div>
  </Separator>
</template>