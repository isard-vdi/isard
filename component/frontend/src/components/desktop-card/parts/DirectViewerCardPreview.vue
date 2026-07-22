<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { DesktopStatusEnum, type BrowserVncValues } from '@/gen/oas/apiv4/'
import NoVNC from '@/components/noVNC/NoVNC.vue'

interface Props {
  status: DesktopStatusEnum
  imageUrl: string
  vncValues: BrowserVncValues | null | undefined
}

const props = defineProps<Props>()

const VNC_ALIVE_STATUSES: DesktopStatusEnum[] = [
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.WAITING_IP,
  DesktopStatusEnum.SHUTTING_DOWN
]

const isVncAlive = computed(() => VNC_ALIVE_STATUSES.includes(props.status))

const root = ref<HTMLDivElement | null>(null)
const inViewport = ref(false)

let observer: IntersectionObserver | null = null

onMounted(() => {
  if (!root.value) return
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
  () => isVncAlive.value && inViewport.value && props.vncValues != null
)
</script>

<template>
  <div ref="root" class="absolute inset-0">
    <div
      class="absolute inset-0 bg-center bg-cover"
      :style="{ backgroundImage: `url(${props.imageUrl})` }"
    />
    <div
      v-if="showLivePreview"
      class="absolute inset-3 rounded-sm ring-1 ring-base-black/70 shadow-lg overflow-hidden bg-gray-warm-900"
    >
      <NoVNC
        :viewer="vncValues!"
        height="100%"
        view-only
        :quality-level="0"
        :compression-level="9"
        background="transparent"
        session-cookie-name="viewerToken"
      />
    </div>
  </div>
</template>
