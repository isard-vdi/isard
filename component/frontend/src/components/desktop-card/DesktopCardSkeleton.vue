<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  variant?: 'stopped' | 'started'
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'stopped'
})
</script>

<template>
  <div
    :class="
      cn(
        'h-full w-full flex flex-row gap-2 items-center justify-start animate-pulse rounded-md bg-gray-warm-300/25 p-2',
        props.class
      )
    "
  >
    <Skeleton class="h-full w-[10px]" />
    <div class="flex flex-col justify-between h-full w-full">
      <div class="flex flex-row gap-2 w-full">
        <Skeleton class="size-10 mr-auto" />
        <Skeleton class="size-10" />
        <Skeleton class="size-10" />
      </div>
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-2 w-full">
          <Skeleton class="h-8" />
          <Skeleton class="h-6" />
        </div>
        <div class="flex flex-row w-full items-center justify-center gap-1 py-2">
          <Skeleton v-if="props.variant === 'stopped'" class="h-10 w-40" />
          <template v-else-if="props.variant === 'started'">
            <Skeleton class="h-10 w-40 mr-auto" />
            <Skeleton class="h-10 w-40" />
            <Skeleton class="size-10" />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
