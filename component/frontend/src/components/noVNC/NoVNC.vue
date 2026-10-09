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

const emit = defineEmits<{ connect: []; disconnect: [] }>()

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
const onConnect = () => emit('connect')
const onDisconnect = () => emit('disconnect')

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
