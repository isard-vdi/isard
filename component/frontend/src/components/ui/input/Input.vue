<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { useVModel } from '@vueuse/core'
import { inputVariants } from '.'

const props = defineProps<{
  defaultValue?: string | number
  modelValue?: string | number
  placeholder?: string
  class?: HTMLAttributes['class']
}>()

const emits = defineEmits<(e: 'update:modelValue', payload: string | number) => void>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue
})

defineOptions({
  inheritAttrs: false
})
</script>

<template>
  <input
    v-model="modelValue"
    data-slot="input"
    v-bind="$attrs"
    :placeholder="props.placeholder"
    :class="inputVariants({ class: props.class })"
  />
</template>
