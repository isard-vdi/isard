<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const STEP_KEYS = [
  'views.direct-viewer.loading.steps.power',
  'views.direct-viewer.loading.steps.viewer'
]

const HOLD_MS = 3600
// Must match the `duration-500` fade below: the text is swapped while it is fully
// transparent, so the change is never caught halfway through the fade.
const FADE_MS = 500

const { t } = useI18n()

const step = ref(0)
const visible = ref(true)
let hold: ReturnType<typeof setInterval> | undefined
let fade: ReturnType<typeof setTimeout> | undefined

// Driven by this component's own lifecycle instead of by a query flag: it is
// only ever mounted while the loading state is on screen, so the rotation cannot
// sit idle behind a visible message.
onMounted(() => {
  hold = setInterval(() => {
    visible.value = false
    fade = setTimeout(() => {
      step.value = (step.value + 1) % STEP_KEYS.length
      visible.value = true
    }, FADE_MS)
  }, HOLD_MS)
})

onUnmounted(() => {
  clearInterval(hold)
  clearTimeout(fade)
})
</script>

<template>
  <p
    class="text-xl text-center text-gray-warm-500 min-h-5 transition-opacity duration-500 ease-in-out motion-reduce:transition-none"
    :class="visible ? 'opacity-100' : 'opacity-0'"
  >
    {{ t(STEP_KEYS[step]) }}
  </p>
</template>
