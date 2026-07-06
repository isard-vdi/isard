<script setup lang="ts">
import type { NotificationFlatItem } from '@/gen/oas/apiv4'
import NotificationCard from './NotificationCard.vue'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

type HeadingLevel = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'

interface Props {
  notifications: NotificationFlatItem[]
  headingLevel?: HeadingLevel
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  headingLevel: 'h2'
})
</script>

<template>
  <ul :class="cn('w-full max-w-[800px] flex flex-col gap-3', props.class)">
    <li v-for="n in props.notifications" :key="n.id" class="w-full">
      <NotificationCard :notification="n" :heading-level="props.headingLevel" />
    </li>
  </ul>
</template>
