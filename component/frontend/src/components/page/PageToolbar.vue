<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div :class="cn('flex w-full flex-col gap-3', props.class)">
    <div v-if="$slots.tabs" class="flex flex-row flex-wrap items-center gap-2">
      <slot name="tabs" />
    </div>

    <div
      v-if="$slots.search || $slots.filters || $slots.actions"
      class="flex w-full flex-row flex-wrap items-start gap-2 sm:gap-4"
    >
      <div
        v-if="$slots.search || $slots.filters"
        class="mr-auto flex min-w-30 flex-1 flex-row items-start gap-2"
      >
        <slot name="search" />
        <slot name="filters" />
      </div>

      <div v-if="$slots.actions" class="flex shrink-0 flex-row items-start gap-2 sm:gap-4">
        <slot name="actions" />
      </div>
    </div>

    <slot name="panel" />
  </div>
</template>
