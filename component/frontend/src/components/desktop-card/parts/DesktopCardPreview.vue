<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

import { DesktopStatusEnum, type UserDesktop, type BrowserVncValues } from '@/gen/oas/apiv4/'
import { getDesktopViewerByType } from '@/gen/oas/apiv4/'

import NoVNC from '@/components/noVNC/NoVNC.vue'
import type { CardSize } from '..'

interface Props {
  desktop: UserDesktop
  imageUrl: string
  size: CardSize
}

const props = defineProps<Props>()

const VNC_ALIVE_STATUSES: DesktopStatusEnum[] = [
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.WAITING_IP,
  DesktopStatusEnum.SHUTTING_DOWN
]

const isVncAlive = computed(() => VNC_ALIVE_STATUSES.includes(props.desktop.status))

// 2xs cards (80px tall) are too small to render a useful noVNC preview; fall
// back to the static image. Everything else gets the live preview.
const previewEnabled = computed(() => props.size !== '2xs')

const root = ref<HTMLDivElement | null>(null)
const inViewport = ref(false)
const viewerValues = ref<BrowserVncValues | null>(null)
const fetchInflight = ref(false)

let observer: IntersectionObserver | null = null

const fetchViewer = async () => {
  if (fetchInflight.value || viewerValues.value) return
  fetchInflight.value = true
  try {
    const { data, error } = await getDesktopViewerByType({
      path: {
        desktop_id: props.desktop.id,
        viewer_type: 'browser-vnc'
      }
    })
    if (error || !data || data.kind !== 'browser' || data.protocol !== 'vnc') return
    viewerValues.value = data.values
  } catch {
    // Network/auth error: fall back to static image silently. The full
    // viewer flow will surface errors when the user clicks to connect.
  } finally {
    fetchInflight.value = false
  }
}

// Drop cached viewer data whenever the desktop leaves the alive set, so the
// next entry into Started picks up fresh credentials (engine rotates
// viewer.passwd on each start).
watch(isVncAlive, (alive) => {
  if (!alive) viewerValues.value = null
})

// Fetch when alive + visible + we don't already have credentials.
watch(
  [isVncAlive, inViewport, previewEnabled],
  ([alive, visible, enabled]) => {
    if (alive && visible && enabled && !viewerValues.value) {
      fetchViewer()
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (!previewEnabled.value || !root.value) return
  observer = new IntersectionObserver(
    (entries) => {
      inViewport.value = entries[0]?.isIntersecting ?? false
    },
    { threshold: 0.01 }
  )
  observer.observe(root.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})

const showLivePreview = computed(
  () => previewEnabled.value && isVncAlive.value && inViewport.value && viewerValues.value !== null
)

// Inset of the noVNC "monitor" inside the card image area, so the static
// image stays visible at the edges as a "desk" around the screen. Scales
// with card size — bigger card, thicker bezel.
const monitorInsetClass = computed(() => {
  switch (props.size) {
    case 'xs':
      return 'inset-1.5'
    case 'sm':
      return 'inset-2'
    case 'md':
      return 'inset-2.5'
    case 'lg':
      return 'inset-3'
    case 'xl':
      return 'inset-4'
    default:
      return 'inset-2'
  }
})
</script>

<template>
  <div ref="root" class="absolute inset-0">
    <div
      class="absolute inset-0 bg-center bg-cover"
      :style="{ backgroundImage: `url(${props.imageUrl})` }"
    />
    <div
      v-if="showLivePreview"
      :class="[
        'absolute rounded-sm ring-1 ring-base-black/70 shadow-lg overflow-hidden bg-gray-warm-900',
        monitorInsetClass
      ]"
    >
      <NoVNC
        :viewer="viewerValues!"
        height="100%"
        view-only
        :quality-level="0"
        :compression-level="9"
        background="transparent"
      />
    </div>
  </div>
</template>
