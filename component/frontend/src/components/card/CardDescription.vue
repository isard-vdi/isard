<template>
  <p class="text-sm text-base-white text-left">
    {{ description }}
  </p>
</template>

<script setup lang="ts">
defineProps<{
  description: string
}>()
</script>
