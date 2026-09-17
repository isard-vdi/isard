<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  // Puts the tabs on the controls row instead of above it, for a toolbar whose
  // tabs and search are the only things on it.
  inlineTabs?: boolean
}>()
</script>

<template>
  <div :class="cn('flex w-full flex-col gap-3', props.class)">
    <div v-if="$slots.tabs && !props.inlineTabs" class="flex flex-row flex-wrap items-center gap-2">
      <slot name="tabs" />
    </div>

    <div
      v-if="$slots.tabs || $slots.view || $slots.search || $slots.filters || $slots.actions"
      class="flex w-full flex-row flex-wrap items-start gap-2 sm:gap-4"
    >
      <div
        v-if="($slots.tabs && props.inlineTabs) || $slots.view || $slots.search || $slots.filters"
        class="mr-auto flex min-w-30 flex-1 flex-row items-start gap-2"
      >
        <slot v-if="props.inlineTabs" name="tabs" />
        <slot name="view" />
        <slot name="search" />
        <slot name="filters" />
      </div>

      <div v-if="$slots.actions" class="flex shrink-0 flex-row items-start gap-2 sm:gap-4">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>
