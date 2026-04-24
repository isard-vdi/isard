<template>
  <h2 class="text-base font-bold mb-1 text-base-white text-left leading-tight">
    {{ title }}
  </h2>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>
