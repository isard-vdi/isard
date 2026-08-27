import { readonly, ref } from 'vue'
import { useEventListener, useRafFn } from '@vueuse/core'

// px/ms. Predicted, not detected: nothing new paints while the main thread renders.
// Only a real fling reaches this; ordinary scrolling peaks well below it and is
// not worth interrupting for.
const ENTER_VELOCITY = 8
// One is all there is time for: waiting for a second confirmation costs a frame,
// and a frame is a whole batch of cards built for a place the fling has already
// left. The threshold above is high enough that a single flick of the wheel
// never reaches it.
const ENTER_SAMPLES = 1
// High on purpose: heavy rows must start rendering while the fling still coasts.
const EXIT_VELOCITY = 2.5
// Once shown it stays put for this long, so it can never read as a flicker.
const MIN_VISIBLE_MS = 150
// Closer than this measures event timing, not the gesture.
const MIN_SAMPLE_MS = 8
// Keeps sampling after the last scroll event, so a coasting fling is measured.
const IDLE_MS = 100

const createVelocitySampler = () => {
  let sampleY = 0
  let sampleAt = 0

  return {
    reset() {
      sampleAt = 0
    },
    // px/ms, or null while there is no wide enough window to measure over.
    read(at: number) {
      if (!sampleAt) {
        sampleY = window.scrollY
        sampleAt = at
        return null
      }

      const elapsed = at - sampleAt
      if (elapsed < MIN_SAMPLE_MS) return null

      const y = window.scrollY
      const velocity = Math.abs(y - sampleY) / elapsed
      sampleY = y
      sampleAt = at
      return velocity
    }
  }
}

// True while the window scrolls faster than a view can keep rendering, for
// views that would rather show a placeholder than the rows they left behind.
export function useFastScroll() {
  const isFastScrolling = ref(false)

  // One sampler each: sharing it left the frame always inside the minimum window.
  const entering = createVelocitySampler()
  const leaving = createVelocitySampler()
  let lastScrollAt = 0
  let fastSamples = 0
  let shownAt = 0

  // Leaving is decided per frame: Vue flushes before the frame callbacks run, so
  // the frame that sees the gesture slow down already has the rows ready to paint.
  const { resume, pause, isActive } = useRafFn(
    ({ timestamp }) => {
      const velocity = leaving.read(timestamp)
      const slowed = velocity !== null && velocity < EXIT_VELOCITY
      if (!slowed && timestamp - lastScrollAt < IDLE_MS) return
      if (isFastScrolling.value && timestamp - shownAt < MIN_VISIBLE_MS) return

      isFastScrolling.value = false
      fastSamples = 0
      pause()
    },
    { immediate: false }
  )

  // Entering is decided on the event itself: a frame later queues the flag
  // behind the very rendering it is meant to cover up. `event.timeStamp` shares
  // the time base of the frame timestamps.
  useEventListener(
    'scroll',
    (event: Event) => {
      lastScrollAt = event.timeStamp

      const velocity = entering.read(event.timeStamp)
      if (velocity !== null) {
        fastSamples = velocity >= ENTER_VELOCITY ? fastSamples + 1 : 0
        if (fastSamples >= ENTER_SAMPLES && !isFastScrolling.value) {
          isFastScrolling.value = true
          shownAt = event.timeStamp
        }
      }

      if (isActive.value) return
      leaving.reset()
      resume()
    },
    { passive: true }
  )

  return { isFastScrolling: readonly(isFastScrolling) }
}
