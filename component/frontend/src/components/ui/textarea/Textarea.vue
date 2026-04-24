<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'

import { useVModel } from '@vueuse/core'
import { cn } from '@/lib/utils'
import { FieldError } from '@/components/ui/field'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<{
  defaultValue?: string | number
  modelValue?: string | number
  placeholder?: string
  destructive?: boolean
  hint?: string
  disabled?: boolean
  errors?: (string | { message: string | undefined } | undefined)[]
  class?: HTMLAttributes['class']
}>()

const emits = defineEmits<{
  (e: 'update:modelValue', payload: string | number): void
  (e: 'blur', event: FocusEvent): void
  (e: 'input', event: Event): void
}>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue
})

// Compute destructive state from errors
const hasErrors = computed(() => props.errors && props.errors.length > 0)
const computedDestructive = computed(() => hasErrors.value || props.destructive)
</script>

<template>
  <textarea
    v-bind="$attrs"
    v-model="modelValue"
    data-slot="textarea"
    :placeholder="placeholder"
    :disabled="disabled"
    :class="
      cn(
        ' border-input placeholder:text-muted-foreground',
        ' focus-visible:border-secondary-3-400 focus-visible:ring-brand',
        ' aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:bg-input/30 flex field-sizing-content min-h-16 w-full rounded-md border bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]',
        'disabled:cursor-not-allowed md:text-sm disabled:bg-gray-warm-100 disabled:border-gray-warm-300',
        computedDestructive &&
          'border-error-300 focus-visible:border-error-300 focus-visible:ring-error-200',
        props.class
      )
    "
    @blur="emits('blur', $event)"
    @input="emits('input', $event)"
  />
  <p v-if="hint" class="text-gray-warm-600 text-sm leading-5 mt-6">{{ hint }}</p>
  <FieldError v-if="hasErrors" class="text-error-600" :errors="errors" />
</template>
