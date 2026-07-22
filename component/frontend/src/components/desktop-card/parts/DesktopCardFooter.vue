<script setup lang="ts">
import { inject, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DesktopStatusEnum } from '@/gen/oas/apiv4/'

import type { DesktopActionsData } from '@/lib/desktops'

import { Button, type ButtonVariants } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { ViewerSelect } from '@/components/viewer-select'

import { CARD_SIZE_INJECTION_KEY } from '..'

const { t } = useI18n()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const buttonSize = computed(() => {
  if (size === 'xl') return 'md' as NonNullable<ButtonVariants['size']>
  if (size === '2xs' || size === 'xs') return 'xs' as NonNullable<ButtonVariants['size']>
  return 'sm' as NonNullable<ButtonVariants['size']>
})

interface Props {
  mainButtonData: DesktopActionsData
  desktopStatus: DesktopStatusEnum
  desktopViewers: string[] // TODO: type this
  preferredViewer?: string // TODO: type this
  desktopIp?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  preferredViewer: undefined,
  desktopIp: null
})

const emit = defineEmits<{
  mainButtonClick: []
  openViewer: [viewer: string]
}>()
</script>

<template>
  <Button
    v-if="props.mainButtonData.actionButton"
    :hierarchy="props.mainButtonData.actionButton.hierarchy"
    :icon="props.mainButtonData.actionButton.icon"
    :icon-class="props.mainButtonData.actionButton.iconClass"
    :size="buttonSize"
    class="shrink-0"
    @click="emit('mainButtonClick')"
  >
    <template v-if="size !== '2xs'">
      {{
        props.mainButtonData.actionButton.label
          ? t(props.mainButtonData.actionButton.label)
          : t(`components.desktops.desktop-card.status.${props.desktopStatus.toLowerCase()}.action`)
      }}
    </template>
  </Button>

  <div
    v-if="props.mainButtonData.text"
    class="flex items-center gap-2 ml-auto mr-auto select-none min-w-0 truncate"
    :class="size === '2xs' ? 'text-xs' : 'text-sm'"
  >
    <Icon
      v-if="props.mainButtonData.text.icon"
      :name="props.mainButtonData.text.icon"
      size="md"
      class="shrink-0"
      :class="props.mainButtonData.text.iconClass"
      :stroke-color="props.mainButtonData.text.iconColor"
    />
    <template v-if="size !== '2xs'">
      {{ t(`components.desktops.desktop-card.status.${props.desktopStatus.toLowerCase()}.text`) }}
    </template>
  </div>

  <ViewerSelect
    v-if="props.mainButtonData.viewers && size !== '2xs'"
    :viewers="
      props.desktopViewers?.map((viewer) => ({
        id: viewer,
        loading: viewer.includes('rdp') && !props.desktopIp
      }))
    "
    :selected-viewer="props.preferredViewer"
    class="ml-auto min-w-0"
    @open-viewer="(viewer) => $emit('openViewer', viewer)"
  />
</template>
