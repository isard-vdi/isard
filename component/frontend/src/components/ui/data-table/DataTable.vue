<script setup lang="ts">
import { useTemplateRef } from 'vue'

interface Props {
  templateCols: string[]
}

const props = withDefaults(defineProps<Props>(), {})

const el = useTemplateRef<HTMLElement>('el')

defineExpose({ el })
</script>

<template>
  <div
    ref="el"
    class="w-full grid gap-0"
    :style="{
      gridTemplateColumns: props.templateCols.join(' ')
    }"
  >
    <slot />
  </div>
</template>
