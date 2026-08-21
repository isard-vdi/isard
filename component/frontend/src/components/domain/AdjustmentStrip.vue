<script setup lang="ts">
import { Icon } from '@/components/icon'

// One line naming what the API changed on its own, plus the items it touched.
// The values themselves are spelled out on the fields, never here.

defineProps<{
  label: string
  items: string[]
}>()
</script>

<template>
  <div
    class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-warning-200 bg-warning-25 px-3 py-2 text-sm text-warning-800"
  >
    <Icon name="alert-triangle" size="sm" stroke-color="warning-800" aria-hidden="true" />
    <span class="font-semibold">{{ label }}</span>
    <span
      v-for="item in items"
      :key="item"
      class="rounded-md border border-warning-200 bg-base-white px-2 py-0.5 text-xs font-medium"
    >
      {{ item }}
    </span>
    <slot name="action" />
  </div>
</template>
