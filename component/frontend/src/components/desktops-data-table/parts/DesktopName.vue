<script setup lang="ts">
import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'

interface Props {
  desktopName: string
  notificationText?: string | null
  notificationTextColor?: string
  notificationIconColor?: string
}

const props = withDefaults(defineProps<Props>(), {
  notificationText: null,
  notificationTextColor: 'gray-warm-500',
  notificationIconColor: 'warning-600'
})
</script>

<template>
  <div class="flex flex-col">
    <p :class="cn('font-bold text-md', props.notificationText ? 'line-clamp-1' : 'line-clamp-2')">
      {{ props.desktopName }}
    </p>

    <div
      v-if="props.notificationText"
      :class="
        cn(
          'inline-flex items-center gap-1.5 font-semibold max-w-full w-max text-xs',
          `text-${props.notificationTextColor}`
        )
      "
    >
      <Icon
        name="info-circle"
        :stroke-color="props.notificationIconColor"
        class="size-3.5 shrink-0"
      />
      <span class="truncate">{{ props.notificationText }}</span>
    </div>
  </div>
</template>
