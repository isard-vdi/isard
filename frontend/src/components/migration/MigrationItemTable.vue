<script setup lang="ts">
import { defineProps } from 'vue'

interface Props {
  items: Array<{
    id: string
    name: string
  }>
}

const props = defineProps<Props>()
</script>

<template>
  <table class="min-w-full bg-white mt-8">
    <thead>
      <tr>
        <th class="py-2">Name</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="item in props.items" :key="item.id">
        <td class="py-2">{{ item.name }}</td>
      </tr>
    </tbody>
  </table>
</template>
