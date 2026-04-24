<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4/'

import { desktopKindStyle as desktopKindStyleFunc } from '@/lib/desktops'

import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem
} from '@/components/ui/context-menu'
import { Icon } from '@/components/icon'

const { t } = useI18n()

interface Props {
  desktop: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  copyToClipboard: [string]
}>()

const desktopKindStyle = computed(() => {
  return desktopKindStyleFunc(props.desktop)
})
</script>

<template>
  <div
    class="flex flex-row gap-0 w-min h-16 rounded-lg overflow-hidden text-secondary-3-600"
    :style="{
      backgroundColor: `var(--${desktopKindStyle.color})`
    }"
  >
    <ContextMenu>
      <ContextMenuTrigger>
        <div class="h-full flex items-center justify-center p-2">
          <Icon :name="desktopKindStyle.icon" :stroke-color="desktopKindStyle.iconColor" />
        </div>
      </ContextMenuTrigger>

      <!-- TODO: centralise desktop debug menu content -->
      <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
        <ContextMenuItem @click="emit('copyToClipboard', props.desktop.id)">{{
          t('components.desktops.desktop-card.debug-options.copy-id')
        }}</ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
    <div
      class="size-16 overflow-hidden shrink-0 rounded-lg object-cover bg-center bg-cover relative"
      :style="{
        backgroundImage: `url(${props.desktop.image?.url ?? ''})`
      }"
    ></div>
  </div>
</template>
