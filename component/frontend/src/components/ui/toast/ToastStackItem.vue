<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { useElementSize } from '@vueuse/core'
import Toast from './Toast.vue'
import type { ToastEntry, ToastId } from './state'

export type ToastPosition =
  | 'top-left'
  | 'top-center'
  | 'top-right'
  | 'bottom-left'
  | 'bottom-center'
  | 'bottom-right'

const GAP = 14
const SCALE_STEP = 0.05

const props = defineProps<{
  toast: ToastEntry
  /** 0 = front / newest. */
  index: number
  /** Cumulative px height of the toasts before this one (for the expanded list). */
  offset: number
  /** Number of visible toasts (for z-index). */
  count: number
  expanded: boolean
  position: ToastPosition
  closeButton: boolean
}>()

const emit = defineEmits<{
  'update:height': [id: ToastId, height: number]
  dismiss: [id: ToastId]
}>()

// Measure the natural height of the card (the inner wrapper is never height-
// constrained, so this stays accurate even while the <li> clips it collapsed).
const measureRef = ref<HTMLElement | null>(null)
const { height } = useElementSize(measureRef)
watch(
  height,
  (h) => {
    if (h > 0) emit('update:height', props.toast.id, h)
  },
  { immediate: true }
)

const isBottom = computed(() => props.position.startsWith('bottom'))
const lift = computed(() => (isBottom.value ? -1 : 1))

// Slide-in on mount: start offset toward the screen edge, then settle.
const mounted = ref(false)
onMounted(() => nextTick(() => (mounted.value = true)))

const transform = computed(() => {
  if (!mounted.value) {
    const x = props.position.endsWith('right') ? 16 : props.position.endsWith('left') ? -16 : 0
    const y = props.position.endsWith('center') ? lift.value * 16 : 0
    return `translate(${x}px, ${y}px)`
  }
  if (props.expanded) {
    return `translateY(${lift.value * props.offset}px)`
  }
  return `translateY(${lift.value * GAP * props.index}px) scale(${1 - SCALE_STEP * props.index})`
})

// Each toast keeps its own measured height in both states; only the transform
// differs (so a taller toast behind a shorter newest one is never cut).
const cssHeight = computed(() => (height.value > 0 ? `${height.value}px` : 'auto'))

const style = computed<CSSProperties>(() => ({
  position: 'absolute',
  left: 0,
  right: 0,
  top: isBottom.value ? 'auto' : 0,
  bottom: isBottom.value ? 0 : 'auto',
  width: '100%',
  zIndex: props.count - props.index,
  height: cssHeight.value,
  overflow: 'visible',
  transform: transform.value,
  transformOrigin: isBottom.value ? 'center bottom' : 'center top',
  // Opacity is animated here but its *value* is owned by the <TransitionGroup>
  // enter/leave classes in Toaster.vue.
  transition:
    'transform 350ms cubic-bezier(0.21,1.02,0.73,1), height 350ms cubic-bezier(0.21,1.02,0.73,1), opacity 300ms ease',
  willChange: 'transform, height'
}))
</script>

<template>
  <li :style="style">
    <div ref="measureRef">
      <Toast :toast="toast" :close-button="closeButton" @dismiss="emit('dismiss', toast.id)" />
    </div>
  </li>
</template>
