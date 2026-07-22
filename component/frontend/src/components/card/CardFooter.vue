<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { HTMLAttributes } from 'vue'

const { t } = useI18n()

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="`h-16 bg-white rounded-b-lg border-x border-b z-1 flex justify-center items-center ${props.class}`"
  >
    <slot />
  </div>
</template>
