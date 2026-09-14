<script setup lang="ts">
import { ref } from 'vue'

import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTextTruncated } from '@/composables/useIsTextTruncated'
import { cardHeaderNotificationVariants } from '@/components/desktop-card'

interface Props {
  desktopName: string
  notificationText?: string | null
  notificationTextColor?: string
  notificationIconColor?: string
  // `dense` puts the notification under the name instead of on its own line of text
  dense?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  notificationText: null,
  notificationTextColor: 'gray-warm-500',
  notificationIconColor: 'warning-600',
  dense: false
})

const nameRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(nameRef, () => props.desktopName)

const notificationRef = ref<HTMLElement | null>(null)
const { isTruncated: isNotificationTruncated } = useIsTextTruncated(
  notificationRef,
  () => props.notificationText
)
</script>

<template>
  <div v-if="props.dense" class="flex min-w-0 flex-col justify-center gap-0.5">
    <Tooltip>
      <TooltipTrigger as-child>
        <p ref="nameRef" class="min-w-0 truncate font-semibold text-sm text-brand-700">
          {{ props.desktopName }}
        </p>
      </TooltipTrigger>
      <TooltipContent v-if="isTruncated" :title="props.desktopName" />
    </Tooltip>

    <Tooltip v-if="props.notificationText">
      <TooltipTrigger as-child>
        <div
          :class="
            cn(
              cardHeaderNotificationVariants({ size: 'md', surface: 'light' }),
              'h-auto items-start py-1 leading-[14px]'
            )
          "
        >
          <Icon name="info-circle" stroke-color="warning-700" class="mt-px h-3.5 w-3.5 shrink-0" />
          <span ref="notificationRef" class="line-clamp-2">{{ props.notificationText }}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent v-if="isNotificationTruncated" :title="props.notificationText" />
    </Tooltip>
  </div>

  <div v-else class="flex flex-col">
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
