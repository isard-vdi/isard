<script setup lang="ts">
import { DraggableItem } from '@/components/drag-and-drop'

const networks = ref<string[]>([...props.selectedNetworks])

const handleReorder = (fromIndex: number, toIndex: number) => {
  const items = [...networks.value]
  const [removed] = items.splice(fromIndex, 1)
  items.splice(toIndex, 0, removed)
  networks.value = items
  // Emit or update form value
}
</script>

<template>
  <div class="space-y-2">
    <DraggableNetworkItem
      v-for="(network, index) in networks"
      :key="network"
      :network="getNetworkByValue(network)"
      :index="index"
      @reorder="handleReorder"
    />
  </div>
</template>
