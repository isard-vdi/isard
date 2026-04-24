<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <Input
    data-slot="input-group-control"
    :class="
      cn(
        'p-0 leading-6 text-base flex-1 rounded-none bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent focus-visible:ring-offset-0',
        props.class
      )
    "
  />
</template>
