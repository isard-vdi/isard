<script setup lang="ts">
import CardBox from '@/components/card-box/CardBox.vue'
</script>

<template>
  <CardBox title="Migration status">
    <template #default>
      <p class="text-lg font-semibold text-gray-900">Migration status</p>
      <p class="text-md font-normal text-gray-600">
        You have no desktops, templates, media or deployments to migrate!
      </p>
    </template>
  </CardBox>
</template>
