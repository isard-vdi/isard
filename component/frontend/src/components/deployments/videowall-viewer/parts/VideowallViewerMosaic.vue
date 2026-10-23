<script setup lang="ts">
import type { VideowallDesktop } from '@/lib/videowall'

import VideowallViewerMosaicTile from './VideowallViewerMosaicTile.vue'
import { MOSAIC_TILE_MIN_WIDTH, type MosaicDensity } from '../constants'

interface Props {
  desktops: VideowallDesktop[]
  density: MosaicDensity
}

const props = defineProps<Props>()

const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto p-4">
    <div
      class="grid gap-3"
      :style="{
        gridTemplateColumns: `repeat(auto-fill, minmax(min(${MOSAIC_TILE_MIN_WIDTH[props.density]}px, 100%), 1fr))`
      }"
    >
      <VideowallViewerMosaicTile
        v-for="tile in props.desktops"
        :key="tile.id"
        :desktop="tile"
        @select="emit('select', tile.id)"
      />
    </div>
  </div>
</template>
