<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4/'

import { desktopKindStyle as desktopKindStyleFunc } from '@/lib/desktops'
import { cn } from '@/lib/utils'

import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem
} from '@/components/ui/context-menu'
import { Icon, type IconVariants } from '@/components/icon'
import DomainImage from '@/components/domain/DomainImage.vue'

const { t } = useI18n()

interface Size {
  frame: string
  thumbnail: string
  swatch: string
  icon: NonNullable<IconVariants['size']>
}

const sizes = {
  sm: {
    frame: 'h-8 rounded-md',
    thumbnail: 'size-8 rounded-md',
    swatch: 'px-1',
    icon: 'sm'
  },
  md: {
    frame: 'h-16 rounded-lg',
    thumbnail: 'size-16 rounded-lg',
    swatch: 'p-2',
    icon: 'md'
  }
} satisfies Record<string, Size>

interface Props {
  desktop: UserDesktop
  size?: keyof typeof sizes
}

const props = withDefaults(defineProps<Props>(), { size: 'sm' })

const size = computed(() => sizes[props.size] ?? sizes.md)

const emit = defineEmits<{
  copyToClipboard: [string]
}>()

const desktopKindStyle = computed(() => {
  return desktopKindStyleFunc(props.desktop)
})
</script>

<template>
  <div
    :class="cn('flex flex-row gap-0 w-min overflow-hidden text-secondary-3-600', size.frame)"
    :style="{
      backgroundColor: `var(--${desktopKindStyle.color})`
    }"
  >
    <ContextMenu>
      <ContextMenuTrigger>
        <div :class="cn('h-full flex items-center justify-center', size.swatch)">
          <Icon
            :name="desktopKindStyle.icon"
            :size="size.icon"
            :stroke-color="desktopKindStyle.iconColor"
          />
        </div>
      </ContextMenuTrigger>

      <!-- TODO: centralise desktop debug menu content -->
      <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
        <ContextMenuItem @click="emit('copyToClipboard', props.desktop.id)">{{
          t('components.desktops.desktop-card.debug-options.copy-id')
        }}</ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
    <DomainImage
      :image-url="props.desktop.image?.url"
      variant="compact"
      :class="cn('shrink-0', size.thumbnail)"
    />
  </div>
</template>
