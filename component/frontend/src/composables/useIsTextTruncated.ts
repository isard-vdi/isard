import { ref, watch, onMounted, toValue, type Ref, type MaybeRefOrGetter } from 'vue'
import { useResizeObserver } from '@vueuse/core'

export function useIsTextTruncated(
  elRef: Ref<HTMLElement | null>,
  textDep?: MaybeRefOrGetter<unknown>,
  // A single-line ellipsis overflows horizontally, a line clamp vertically.
  // Checking both would report every one-line element as truncated, because
  // `scrollHeight` rounds a fractional line height up past `clientHeight`.
  axis: 'x' | 'y' = 'x'
) {
  // Reactive state that will indicate if the text is truncated or not
  const isTruncated = ref(false)

  // Checks if the element's content overflows its box
  const check = () => {
    const el = elRef.value

    // if the element is not yet available in the DOM, exit
    if (!el) return

    // scrollWidth/scrollHeight = full content size
    // clientWidth/clientHeight = visible size
    // If content is bigger than the container it's truncated
    isTruncated.value =
      axis === 'y' ? el.scrollHeight > el.clientHeight : el.scrollWidth > el.clientWidth
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
