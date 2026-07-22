<script setup lang="ts">
import DesktopCardBase from './DesktopCardBase.vue'
import { type CardSize } from '.'

interface Props {
  desktopKind: 'persistent' | 'nonpersistent' | 'deployment'
  imageUrl: string
  showOverlay?: boolean
  size?: CardSize
  fill?: boolean
}

withDefaults(defineProps<Props>(), {
  showOverlay: false,
  size: 'lg',
  fill: false
})
</script>

<template>
  <div class="relative pl-[18px]">
    <!-- Strip 2: furthest back, shortest, darkest -->
    <div
      class="absolute left-[-2px] z-0 top-1/2 -translate-y-1/2 w-[30px] h-[270px] shrink-0 rounded-l-[10px] bg-secondary-2-800"
    />

    <!-- Strip 1: middle, taller, medium -->
    <div
      class="absolute left-[8px] z-[1] top-1/2 -translate-y-1/2 w-[30px] h-[290px] shrink-0 rounded-l-[10px] bg-secondary-2-700"
    />

    <!-- Main card: on top -->
    <div class="relative z-[2]">
      <DesktopCardBase
        :desktop-kind="desktopKind"
        :image-url="imageUrl"
        :show-overlay="showOverlay"
        :size="size"
        :fill="fill"
      >
        <template v-if="$slots['debug-options-content']" #debug-options-content>
          <slot name="debug-options-content" />
        </template>
        <template v-if="$slots['header-actions']" #header-actions>
          <slot name="header-actions" />
        </template>
        <template v-if="$slots['header']" #header>
          <slot name="header" />
        </template>
        <template v-if="$slots['footer']" #footer>
          <slot name="footer" />
        </template>
        <template v-if="$slots['overlay']" #overlay>
          <slot name="overlay" />
        </template>
      </DesktopCardBase>
    </div>
  </div>
</template>
