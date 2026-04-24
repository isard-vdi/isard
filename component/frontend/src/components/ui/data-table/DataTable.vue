<script setup lang="ts">
interface Props {
  templateCols: string[]
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div
    class="w-full grid gap-0"
    :style="{
      gridTemplateColumns: props.templateCols.join(' ')
    }"
  >
    <slot />
  </div>
</template>
