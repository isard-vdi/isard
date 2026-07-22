<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
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
}

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
}

onMounted(() => {
  if (screen.value) {
    newRFB(screen.value)
  }
})

onBeforeUnmount(() => {
  if (rfb) {
    rfb.disconnect()
    rfb = null
  }
})
</script>

<template>
  <div :style="`height: ${props.height}; width: 100%;`">
    <div
      ref="screen"
      :style="`height: 100%; width: 100%; pointer-events: ${props.viewOnly ? 'none' : 'auto'};`"
    />
  </div>
</template>
