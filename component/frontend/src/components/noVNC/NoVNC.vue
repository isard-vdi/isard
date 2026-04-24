<script setup lang="ts">
import { ref, onMounted } from 'vue'
import RFB from '@novnc/novnc/core/rfb'

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
  background?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '750px',
  viewOnly: false,
  qualityLevel: 6,
  background: 'var(--gray-warm-800)'
})

const screen = ref<HTMLElement | null>(null)
let rfb: InstanceType<typeof RFB> | null = null

const getCookie = (name: string) => {
  const value = `; ${document.cookie}`
  const parts = value.split(`; ${name}=`)
  if (parts.length === 2) return parts.pop()?.split(';').shift()
}

const newRFB = (
  target: HTMLElement,
  viewOnly: boolean,
  qualityLevel: number,
  background: string
) => {
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
    getCookie('isardvdi_session')

  rfb = new RFB(target, wsUrl, {
    credentials: { password: props.viewer.token }
  })

  rfb.viewOnly = viewOnly
  rfb.qualityLevel = qualityLevel
  rfb.scaleViewport = true
  rfb.background = background
}

onMounted(() => {
  if (screen.value) {
    newRFB(screen.value, props.viewOnly, props.qualityLevel, props.background)
  }
})
</script>

<template>
  <div>
    <div ref="screen" :style="`height: ${props.height}; cursor: pointer;`" />
  </div>
</template>
