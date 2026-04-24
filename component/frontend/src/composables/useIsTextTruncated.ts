import { ref, watch, onMounted, toValue, type Ref, type MaybeRefOrGetter } from 'vue'
import { useResizeObserver } from '@vueuse/core'

export function useIsTextTruncated(
  elRef: Ref<HTMLElement | null>,
  textDep?: MaybeRefOrGetter<unknown>
) {
  // Reactive state that will indicate if the text is truncated or not
  const isTruncated = ref(false)

  // Checks if the element's content overflows horizontally
  const check = () => {
    const el = elRef.value

    // if the element is not yet available in the DOM, exit
    if (!el) return

    // scrollWidth = full content width
    // clientWidth = visible witdh
    // If content is wider than the container it's truncated
    isTruncated.value = el.scrollWidth > el.clientWidth
  }

  // Observe element size changes
  useResizeObserver(elRef, check)
  onMounted(check)

  if (textDep !== undefined) {
    watch(
      () => toValue(textDep),
      () => {
        queueMicrotask(check)
      }
    )
  }

  return { isTruncated }
}
