<script setup lang="ts">
import type { AvatarFallbackProps } from 'reka-ui'
import { AvatarFallback } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
const props = defineProps<AvatarFallbackProps & { class?: HTMLAttributes['class'] }>()
</script>

<template>
  <AvatarFallback v-bind="props" :class="props.class">
    <slot />
  </AvatarFallback>
</template>
