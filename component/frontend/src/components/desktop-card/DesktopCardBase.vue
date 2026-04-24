<script setup lang="ts">
import { computed, provide } from 'vue'
import { useI18n } from 'vue-i18n'
import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'
import { ContextMenu, ContextMenuTrigger } from '@/components/ui/context-menu'

import type { CardSize } from '.'
import {
  CARD_SIZE_INJECTION_KEY,
  cardBaseVariants,
  cardImageVariants,
  cardGradientVariants,
  cardHeaderActionsVariants,
  cardHeaderSlotVariants,
  cardFooterVariants,
  cardIconTriggerVariants,
  cardIpAreaVariants,
  cardNetworkVariants
} from '.'
const { t, d } = useI18n()

interface Props {
  desktopKind: 'persistent' | 'nonpersistent' | 'deployment'
  imageUrl: string
  showNetworkOverlay?: boolean
  size?: CardSize
  fill?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showNetworkOverlay: false,
  size: 'lg',
  fill: false
})

provide(CARD_SIZE_INJECTION_KEY, props.size)

const showSvgDecoration = computed(() => props.size !== '2xs')

const svgScale = computed(() => {
  const scales: Record<CardSize, number> = {
    '2xs': 0,
    xs: 0.5,
    sm: 0.65,
    md: 0.8,
    lg: 1,
    xl: 1.15
  }
  return scales[props.size]
})

const desktopKindStyle = computed(() => {
  switch (props.desktopKind) {
    case 'persistent':
      return {
        color: 'secondary-3-500',
        icon: 'browser',
        iconColor: 'secondary-3-600'
      }
    case 'nonpersistent':
      return {
        color: 'secondary-1-500',
        icon: 'clock',
        iconColor: 'secondary-1-600'
      }
    case 'deployment':
      return {
        color: 'secondary-2-500',
        icon: 'layout-alt-04',
        iconColor: 'secondary-2-600'
      }

    default:
      return {
        color: 'error-500',
        icon: 'help-circle',
        iconColor: 'error-800'
      }
  }
})
</script>

<template>
  <div
    :class="cn(cardBaseVariants({ size, fill }), `border-l-${desktopKindStyle.color}`)"
    :style="{
      borderLeftColor: `var(--${desktopKindStyle.color})`
    }"
  >
    <div class="relative flex flex-col h-full w-full">
      <!-- SVG decoration + icon trigger (shown for xs and above) -->
      <div v-if="showSvgDecoration" class="absolute top-0 left-0 z-10">
        <div class="flex flex-row">
          <div
            class="select-none origin-top-left"
            :class="`text-${desktopKindStyle.color}`"
            :style="{
              color: `var(--${desktopKindStyle.color})`,
              transform: svgScale !== 1 ? `scale(${svgScale})` : undefined
            }"
          >
            <svg
              width="40"
              height="114"
              viewBox="0 0 40 114"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M39.9 0.00976562V30C39.9 39.9411 31.8411 48 21.9 48H17.9098C7.96867 48 -0.09021 56.0589 -0.09021 66V104C-0.09021 109.523 -4.56736 114 -10.0902 114C-10.0955 114 -10.0999 113.996 -10.1 113.99V30C-10.1 27.2386 -7.8614 25 -5.09998 25C-2.33855 25 -0.0999756 22.7614 -0.0999756 20V0.00976562C-0.0998533 0.00442859 -0.0955469 0.000122692 -0.09021 0H39.8903C39.8956 0.000122334 39.8999 0.00442866 39.9 0.00976562Z"
                fill="currentColor"
              />
            </svg>
          </div>

          <ContextMenu>
            <ContextMenuTrigger :class="cn(cardIconTriggerVariants({ size }), 'rounded-br-2xl')">
              <Icon :name="desktopKindStyle.icon" :stroke-color="desktopKindStyle.iconColor" />
            </ContextMenuTrigger>
            <slot name="debug-options-content" />
          </ContextMenu>
        </div>
      </div>

      <!-- Simplified icon for 2xs (no SVG decoration) -->
      <div v-else class="absolute top-0 left-0 z-10">
        <ContextMenu>
          <ContextMenuTrigger class="flex items-center justify-center w-[20px] h-5">
            <Icon
              :name="desktopKindStyle.icon"
              :stroke-color="desktopKindStyle.iconColor"
              class="h-3 w-3"
            />
          </ContextMenuTrigger>
          <slot name="debug-options-content" />
        </ContextMenu>
      </div>

      <div
        :class="cardImageVariants({ size })"
        :style="{
          backgroundImage: `url(${props.imageUrl})`
        }"
      >
        <div :class="cardHeaderActionsVariants({ size })">
          <slot name="header-actions" />
        </div>

        <div :class="cardGradientVariants({ size })" />

        <template v-if="showNetworkOverlay">
          <div class="absolute inset-0 bg-base-black/60 transition-opacity duration-300 z-0" />

          <div :class="cardIpAreaVariants({ size })">
            <slot name="ip" />
          </div>

          <div :class="cardNetworkVariants({ size })">
            <slot name="networks" />
          </div>

          <div class="border-b border-white pb-2 mb-2 z-10" />
        </template>

        <div :class="cardHeaderSlotVariants({ size })">
          <slot name="header" />
        </div>
      </div>

      <div :class="cardFooterVariants({ size })">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
