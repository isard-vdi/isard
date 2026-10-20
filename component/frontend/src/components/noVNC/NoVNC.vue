<script setup lang="ts">
import { ref, watch, onMounted, type HTMLAttributes, onBeforeUnmount } from 'vue'
import RFB from '@novnc/novnc'

interface Props {
  viewer: {
    host: string
    port?: string
    vmHost: string
    vmPort: string
    token: string
  }
  height?: string
  viewOnly?: boolean
  qualityLevel?: number // From 0 to 9. Default is 6
  compressionLevel?: number // From 0 to 9. Leave unset to use noVNC default (2)
  background?: string
  sessionCookieName?: string
  class?: HTMLAttributes['class']
}

const emit = defineEmits<{ connect: []; disconnect: []; firstFrame: [] }>()

const props = withDefaults(defineProps<Props>(), {
  height: '750px',
  viewOnly: false,
  qualityLevel: 6,
  compressionLevel: undefined,
  background: 'var(--gray-warm-800)',
  sessionCookieName: 'isardvdi_session'
})

const screen = ref<HTMLElement | null>(null)
let rfb: InstanceType<typeof RFB> | null = null

// noVNC connects before the first frame reaches the canvas: until it does, the screen is blank.
const FIRST_FRAME_POLL_MS = 100
let firstFrameTimer: ReturnType<typeof setInterval> | undefined
let probe: CanvasRenderingContext2D | null = null
const stopFirstFrameWatch = () => clearInterval(firstFrameTimer)
const watchFirstFrame = () => {
  stopFirstFrameWatch()
  firstFrameTimer = setInterval(() => {
    const canvas = screen.value?.querySelector('canvas')
    if (!canvas || canvas.width === 0 || canvas.height === 0) return
    // Framebuffer pixels are opaque; the canvas starts transparent. Read a copy of the centre
    // pixel: reading noVNC's canvas itself makes the browser warn on every poll.
    probe ??= document.createElement('canvas').getContext('2d', { willReadFrequently: true })
    if (!probe) return
    probe.clearRect(0, 0, 1, 1)
    probe.drawImage(canvas, canvas.width >> 1, canvas.height >> 1, 1, 1, 0, 0, 1, 1)
    if ((probe.getImageData(0, 0, 1, 1).data[3] ?? 0) > 0) {
      stopFirstFrameWatch()
      emit('firstFrame')
    }
  }, FIRST_FRAME_POLL_MS)
}

const onConnect = () => {
  emit('connect')
  watchFirstFrame()
}
const onDisconnect = () => {
  stopFirstFrameWatch()
  emit('disconnect')
}

const getCookie = (name: string) => {
  const value = `; ${document.cookie}`
  const parts = value.split(`; ${name}=`)
  if (parts.length === 2) return parts.pop()?.split(';').shift()
}

const newRFB = (target: HTMLElement) => {
  const wsUrl =
    'wss://' +
    props.viewer.host +
    ':' +
    props.viewer.port +
    '/' +
    props.viewer.vmHost +
    '/' +
    props.viewer.vmPort +
    '/' +
    getCookie(props.sessionCookieName)

  rfb = new RFB(target, wsUrl, {
    credentials: { password: props.viewer.token }
  })

  rfb.viewOnly = props.viewOnly
  rfb.qualityLevel = props.qualityLevel
  if (props.compressionLevel !== undefined) {
    rfb.compressionLevel = props.compressionLevel
  }
  rfb.scaleViewport = true
  rfb.background = props.background
  rfb.addEventListener('connect', onConnect)
  rfb.addEventListener('disconnect', onDisconnect)
}

// Live switch, no reconnect: noVNC also releases or takes back the keyboard.
watch(
  () => props.viewOnly,
  (viewOnly) => {
    if (rfb) rfb.viewOnly = viewOnly
  }
)

onMounted(() => {
  if (screen.value) {
    newRFB(screen.value)
  }
})

// Our own teardown is not the connection failing: stop listening before closing.
onBeforeUnmount(() => {
  stopFirstFrameWatch()
  if (rfb) {
    rfb.removeEventListener('connect', onConnect)
    rfb.removeEventListener('disconnect', onDisconnect)
    rfb.disconnect()
    rfb = null
  }
})
</script>

<template>
  <div
    ref="screen"
    :style="`height: ${props.height}; width: 100%; pointer-events: ${props.viewOnly ? 'none' : 'auto'};`"
    :class="props.class"
  />
</template>
