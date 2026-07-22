<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
import { useSidebar } from './utils'
import { Icon } from '@/components/icon'

const props = defineProps<{
  class?: HTMLAttributes['class']
  icon?: string
}>()

const { toggleSidebar } = useSidebar()
</script>

<template>
  <Icon
    size="lg"
    :name="props.icon ? props.icon : 'layout-left'"
    :class="cn(props.class)"
    alt="Toggle Sidebar"
    stroke-color="gray-warm-700"
    @click="toggleSidebar"
  >
  </Icon>
</template>
