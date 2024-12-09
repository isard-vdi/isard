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
  <div class="w-full bg-base-white rounded-xl border border-gray-warm-300 p-4">
    <table class="min-w-full bg-base-white">
      <thead>
        <tr class="border-b border-gray-warm-300">
          <th class="py-2 text-start text-gray-warm-600">Name</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in props.items" :key="item.id" class="border-b border-gray-warm-300 last:border-b-0">
          <td class="py-2">{{ item.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
