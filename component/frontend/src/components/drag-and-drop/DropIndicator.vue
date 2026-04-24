<script setup lang="ts">
import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/types'

const { edge, gap } = defineProps<{
  edge: Edge
  gap: string
}>()

type Orientation = 'horizontal' | 'vertical'

const edgeToOrientationMap: Record<Edge, Orientation> = {
  top: 'horizontal',
  bottom: 'horizontal',
  left: 'vertical',
  right: 'vertical'
}

const orientationStyles: Record<Orientation, string> = {
  horizontal:
    'h-[--line-thickness] left-[--terminal-radius] right-0 before:left-[--negative-terminal-size]',
  vertical:
    'w-[--line-thickness] top-[--terminal-radius] bottom-0 before:top-[--negative-terminal-size]'
}

const edgeStyles: Record<Edge, string> = {
  top: 'top-[--line-offset] before:top-[--offset-terminal]',
  right: 'right-[--line-offset] before:right-[--offset-terminal]',
  bottom: 'bottom-[--line-offset] before:bottom-[--offset-terminal]',
  left: 'left-[--line-offset] before:left-[--offset-terminal]'
}

const strokeSize = 2
const terminalSize = 8
const offsetToAlignTerminalWithLine = (strokeSize - terminalSize) / 2
</script>

<template>
  <div
    :class="[
      orientationStyles[edgeToOrientationMap[edge]],
      [edgeStyles[edge]],
      'absolute z-10 bg-blue-700 pointer-events-none before:content[\'\'] before:w-[--terminal-size] before:h-[--terminal-size] box-border before:absolute before:border-[length:--line-thickness] before:border-solid before:border-blue-700 before:rounded-full'
    ]"
    :style="{
      '--line-thickness': `${strokeSize}px`,
      '--line-offset': `calc(-0.5 * (${gap} + ${strokeSize}px))`,
      '--terminal-size': `${terminalSize}px`,
      '--terminal-radius': `${terminalSize / 2}px`,
      '--negative-terminal-size': `-${terminalSize}px`,
      '--offset-terminal': `${offsetToAlignTerminalWithLine}px`
    }"
  />
</template>
