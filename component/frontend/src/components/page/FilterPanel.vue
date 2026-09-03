<script setup lang="ts">
defineProps<{
  open: boolean
}>()
</script>

<template>
  <div v-show="open" class="flex w-full flex-row flex-wrap items-center gap-4">
    <div v-if="$slots.default" class="mr-auto flex flex-row flex-wrap gap-2">
      <slot />
    </div>
    <slot name="end" />
  </div>
</template>
