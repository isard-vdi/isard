<script setup lang="ts">
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'

withDefaults(
  defineProps<{
    icon?: string
    label?: string
    loading?: boolean
  }>(),
  {
    icon: undefined,
    label: undefined,
    loading: false
  }
)
</script>

<template>
  <div class="grid grid-cols-1 items-start sm:grid-cols-[11rem_1fr] gap-x-10 gap-y-2 py-3">
    <div class="flex items-center gap-2 text-brand-700">
      <template v-if="loading">
        <Skeleton class="h-4 w-4 rounded" />
        <Skeleton class="h-5 w-24" />
      </template>
      <template v-else>
        <Icon v-if="icon" aria-hidden="true" :name="icon" size="sm" stroke-color="" />
        <span class="text-sm font-bold uppercase tracking-wide">{{ label }}</span>
      </template>
    </div>
    <div class="flex flex-wrap items-center gap-x-7 gap-y-2">
      <template v-if="loading">
        <Skeleton class="h-5 w-28" />
        <Skeleton class="h-5 w-20" />
        <Skeleton class="h-5 w-24" />
      </template>
      <slot v-else />
    </div>
  </div>
</template>
