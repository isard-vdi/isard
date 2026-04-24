<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { Primitive } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends PrimitiveProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'code'
})
</script>

<template>
  <Primitive
    :as="props.as"
    :class="cn('px-1 py-0.5 rounded-sm bg-gray-warm-200 font-mono text-gray-warm-800', props.class)"
    ><slot
  /></Primitive>
</template>
