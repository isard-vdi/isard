<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <main :class="cn('mx-auto flex w-full max-w-480 flex-1 flex-col gap-6', props.class)">
    <slot />
  </main>
</template>
