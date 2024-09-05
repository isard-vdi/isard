<script lang="ts" setup>
import { type HTMLAttributes, provide, computed, inject } from 'vue'
import { useId } from 'radix-vue'
import { FieldContextKey, useFieldError } from 'vee-validate'
import { FORM_ITEM_INJECTION_KEY } from './injectionKeys'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const id = useId()
provide(FORM_ITEM_INJECTION_KEY, id)

const cls = computed(() => {
  let cls = cn('space-y-2', props.class)

  const fieldContext = inject(FieldContextKey)
  if (!fieldContext) throw new Error('useFormField should be used within <FormField>')

  const error = useFieldError(fieldContext.name)
  if (error.value && error.value !== '') {
    cls += ' [&>input]:ring [&>input]:ring-error'
  }

  return cls
})
</script>

<template>
  <div :class="cls">
    <slot />
  </div>
</template>
