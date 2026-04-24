<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { draggable, dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine'
import {
  attachClosestEdge,
  extractClosestEdge
} from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'
import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/types'
import { DropIndicator } from '@/components/drag-and-drop'

interface Props {
  item: { value: string; label: string }
  index: number
  canReorder?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canReorder: true
})
const emit = defineEmits<{
  reorder: [fromIndex: number, toIndex: number]
}>()

type ItemState =
  | {
      type: 'idle'
    }
  | {
      type: 'preview'
      container: HTMLElement
    }
  | {
      type: 'is-dragging'
    }
  | {
      type: 'is-dragging-over'
      closestEdge: Edge | null
    }

const stateStyles: { [Key in ItemState['type']]?: string } = {
  'is-dragging': 'opacity-40'
}

const idle: ItemState = { type: 'idle' }
const elRef = ref<HTMLElement | null>(null)
const elState = ref<ItemState>(idle)

let cleanup: () => void = () => {
  /* noop — replaced on mount */
}

onMounted(() => {
  if (!elRef.value) return

  cleanup = combine(
    draggable({
      element: elRef.value,
      getInitialData: () => ({ index: props.index, item: props.item }),
      onDragStart: () => {
        elState.value = { type: 'is-dragging' }
      },
      onDrop: () => {
        elState.value = idle
      }
    }),
    ...(props.canReorder
      ? [
          dropTargetForElements({
            element: elRef.value,
            canDrop: ({ source }) => {
              const sourceItem = source.data.item as { value: string; label: string }
              return sourceItem.value !== props.item.value
            },
            getData: ({ input, element }) => {
              return attachClosestEdge(
                { index: props.index, item: props.item },
                {
                  element,
                  input,
                  allowedEdges: ['top', 'bottom']
                }
              )
            },
            getIsSticky() {
              return true
            },
            onDragEnter: ({ self, source }) => {
              const closestEdge = extractClosestEdge(self.data)
              elState.value = { type: 'is-dragging-over', closestEdge }
            },
            onDrag: ({ self, source }) => {
              const closestEdge = extractClosestEdge(self.data)

              // Only need to update react state if nothing has changed.
              if (
                elState.value.type !== 'is-dragging-over' ||
                elState.value.closestEdge !== closestEdge
              ) {
                elState.value = { type: 'is-dragging-over', closestEdge }
              }
            },
            onDragLeave: () => {
              elState.value = idle
            },
            onDrop: () => {
              elState.value = idle
            }
          })
        ]
      : [])
  )

  onUnmounted(cleanup)
})
</script>

<template>
  <div
    ref="elRef"
    :data-item-id="props.item.value"
    :class="[
      'relative flex items-center gap-2 p-2 border border-gray-warm-200 rounded bg-white transition-all duration-200',
      'hover:shadow-sm hover:cursor-grab active:cursor-grabbing',
      stateStyles[elState.type] ?? ''
    ]"
  >
    <slot :item="props.item">
      <span class="text-sm text-gray-warm-900">{{ props.item.label }}</span>
    </slot>
  </div>
  <!-- Drop indicator -->
  <DropIndicator
    v-if="props.canReorder && elState.type === 'is-dragging-over' && elState.closestEdge"
    :edge="elState.closestEdge"
    gap="8px"
  />
</template>
