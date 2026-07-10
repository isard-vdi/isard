<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { CSSProperties, HTMLAttributes } from 'vue'
import { useEventListener } from '@vueuse/core'
import { cn } from '@/lib/utils'
import ToastStackItem from './ToastStackItem.vue'
import type { ToastPosition } from './ToastStackItem.vue'
import { pauseTimers, remove, resumeTimers, toasts } from './state'
import type { ToastId } from './state'

const GAP = 14

const props = withDefaults(
  defineProps<{
    position?: ToastPosition
    /** Global default for the per-toast close button. */
    closeButton?: boolean
    /** Maximum number of toasts kept in the stack (most recent). */
    visibleToasts?: number
    class?: HTMLAttributes['class']
  }>(),
  {
    position: 'top-right',
    closeButton: true,
    visibleToasts: 3,
    class: undefined
  }
)

// Tracked apart: releasing one must not resume the countdowns while the other
// still holds the stack (e.g. tabbing out of a toast the cursor rests on).
const hovered = ref(false)
const focused = ref(false)

// Stack expands to a full vertical list while hovered or focused.
const expanded = computed(() => hovered.value || focused.value)

watch(expanded, (isExpanded) => {
  if (isExpanded) pauseTimers()
  // Don't restart the countdowns behind a backgrounded tab.
  else if (document.hasFocus()) resumeTimers()
})

// Natural height of each toast, reported by the stack items.
const heights = reactive(new Map<ToastId, number>())
const setHeight = (id: ToastId, height: number) => heights.set(id, height)
const onDismiss = (id: ToastId) => remove(id)

// Toasts also leave the queue without passing through `onDismiss` (auto-close,
// programmatic `toast.dismiss()`), so drop their heights here rather than there.
// Watching the mapped ids, not `toasts` itself: a plain ref watch is shallow and
// would miss the in-place `splice()` that `remove()` performs.
watch(
  () => toasts.value.map((entry) => entry.id),
  (ids) => {
    const alive = new Set(ids)
    heights.forEach((_, id) => {
      if (!alive.has(id)) heights.delete(id)
    })
  }
)

// Most recent toasts, newest first (index 0 = front of the stack).
const visible = computed(() => toasts.value.slice(-props.visibleToasts).reverse())

const frontHeight = computed(() =>
  visible.value.length ? (heights.get(visible.value[0].id) ?? 0) : 0
)

// Cumulative offset (px) of each toast for the expanded vertical list.
const offsets = computed(() => {
  const out: number[] = []
  let acc = 0
  visible.value.forEach((item, i) => {
    out.push(acc + i * GAP)
    acc += heights.get(item.id) ?? 0
  })
  return out
})

const containerHeight = computed(() => {
  if (!visible.value.length) return 'auto'
  if (!expanded.value) return frontHeight.value > 0 ? `${frontHeight.value}px` : 'auto'
  const total = visible.value.reduce((sum, item) => sum + (heights.get(item.id) ?? 0), 0)
  const h = total + (visible.value.length - 1) * GAP
  return h > 0 ? `${h}px` : 'auto'
})

const positionClasses: Record<ToastPosition, string> = {
  'top-left': 'top-4 left-4',
  'top-center': 'top-4 left-1/2 -translate-x-1/2',
  'top-right': 'top-4 right-4',
  'bottom-left': 'bottom-4 left-4',
  'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2',
  'bottom-right': 'bottom-4 right-4'
}

const listStyle = computed<CSSProperties>(() => ({
  height: containerHeight.value,
  transition: 'height 350ms cubic-bezier(0.21,1.02,0.73,1)'
}))

// Release focus only when it actually leaves the stack, not on moves within it.
function onFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as Node | null
  if (!next || !(event.currentTarget as HTMLElement).contains(next)) focused.value = false
}

// Freeze the countdowns while the tab/window is backgrounded.
useEventListener(window, 'blur', pauseTimers)
useEventListener(window, 'focus', () => {
  if (!expanded.value) resumeTimers()
})
</script>

<template>
  <Teleport to="body">
    <!-- Outer scroll container: when expanded (column), the inner <ol> (real
         height) overflows this box, so it scrolls instead of running off-screen. -->
    <div
      :class="
        cn(
          'pointer-events-auto fixed z-[100] w-[356px] max-w-[calc(100vw-2rem)]',
          positionClasses[props.position],
          expanded
            ? 'max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden'
            : 'overflow-visible',
          props.class
        )
      "
      role="region"
      aria-label="Notifications"
      @mouseenter="hovered = true"
      @mouseleave="hovered = false"
      @focusin="focused = true"
      @focusout="onFocusOut"
    >
      <TransitionGroup
        tag="ol"
        class="relative m-0 block list-none p-0"
        :style="listStyle"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <ToastStackItem
          v-for="(item, i) in visible"
          :key="item.id"
          :toast="item"
          :index="i"
          :offset="offsets[i]"
          :count="visible.length"
          :expanded="expanded"
          :position="props.position"
          :close-button="props.closeButton"
          @update:height="setHeight"
          @dismiss="onDismiss"
        />
      </TransitionGroup>
    </div>
  </Teleport>
</template>
