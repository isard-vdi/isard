<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'

interface Props {
  /**
   * MIME type of the file (e.g., "Document/PDF", "Image/PNG")
   */
  fileType: string
}

const props = defineProps<Props>()

const fileExtension = computed(() => {
  const parts = props.fileType.split('/')
  if (parts.length > 1) {
    return parts[1].toUpperCase()
  }
  return props.fileType.slice(0, 3).toUpperCase()
})

const bgColor = computed(() => {
  const fileType = props.fileType.toUpperCase()

  if (fileType.includes('PDF') || fileType.includes('PPT')) {
    return 'bg-error-600'
  } else if (fileType.includes('TXT')) {
    return 'bg-gray-warm-700'
  } else if (fileType.includes('CSV') || fileType.includes('XLS')) {
    return 'bg-[hsla(151,88%,30%,1)]'
  } else if (
    fileType.includes('HTML') ||
    fileType.includes('CSS') ||
    fileType.includes('JSON') ||
    fileType.includes('XML')
  ) {
    return 'bg-[hsla(237,77%,59%,1)]'
  } else if (fileType.includes('DOC')) {
    return 'bg-[hsla(220,87%,51%,1)]'
  } else {
    return 'bg-brand-600'
  }
})
</script>

<template>
  <div class="relative w-10 h-10">
    <Icon name="file-04" stroke-color="gray-warm-300" fill-color="base-white" class="h-10 w-10" />
    <div
      class="absolute top-1/2 left-1 -translate-y-1/3 -translate-x-1/3 rounded-sm text-base-white text-[10px] py-1/2 px-1 font-bold text-center"
      :class="bgColor"
    >
      {{ fileExtension.slice(0, 4) }}
    </div>
  </div>
</template>
