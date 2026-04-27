<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { UserDesktop } from '@/gen/oas/apiv4/'

import { DesktopCardHeaderActionsDropdownContent } from '..'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const { t } = useI18n()

interface Props {
  desktop: UserDesktop
  // Currently shown overlay; the matching icon is highlighted so users see
  // which panel is open and which icon will close it on next click.
  activeOverlay?: 'info' | 'networks' | 'bastion' | null
}

const props = withDefaults(defineProps<Props>(), {
  activeOverlay: null
})

const emit = defineEmits<{
  infoClick: []
  networkClick: []
  bastionClick: []
  editDesktop: []
  showDeleteModal: []
  showDirectLinkModal: []
  showRecreateModal: []
  createTemplate: []
  bookDesktop: []
  changeImage: []
  showStorageModal: []
}>()

const bastionEnabled =
  props.desktop.bastion_target?.http?.enabled || props.desktop.bastion_target?.ssh?.enabled

// Highlighted state when this icon's overlay is the active one.
const iconButtonClass = (active: boolean) =>
  [
    'w-9! h-9! flex align-center justify-center p-0! backdrop-blur-[4px]',
    active ? 'bg-base-white/30 hover:bg-base-white/40' : 'bg-base-black/30 hover:bg-base-black/50'
  ].join(' ')
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        hierarchy="link-gray"
        size="sm"
        :class="iconButtonClass(props.activeOverlay === 'info')"
        icon="info-circle"
        icon-stroke-color="base-white"
        @click="emit('infoClick')"
      />
    </TooltipTrigger>
    <TooltipContent :title="t('components.desktops.desktop-card.actions.info')" />
  </Tooltip>

  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        hierarchy="link-gray"
        size="sm"
        :class="iconButtonClass(props.activeOverlay === 'networks')"
        icon="modem-02"
        icon-stroke-color="base-white"
        @click="emit('networkClick')"
      />
    </TooltipTrigger>
    <TooltipContent :title="t('components.desktops.desktop-card.actions.networks')" />
  </Tooltip>

  <Tooltip v-if="bastionEnabled">
    <TooltipTrigger as-child>
      <Button
        hierarchy="link-gray"
        size="sm"
        :class="iconButtonClass(props.activeOverlay === 'bastion')"
        icon="globe-04"
        icon-stroke-color="base-white"
        @click="emit('bastionClick')"
      />
    </TooltipTrigger>
    <TooltipContent :title="t('components.desktops.desktop-card.actions.bastion-access')" />
  </Tooltip>

  <DropdownMenu>
    <DropdownMenuTrigger>
      <Button
        hierarchy="link-gray"
        size="sm"
        class="w-9! h-9! flex align-center justify-center bg-base-black/30 hover:bg-base-black/50 p-0! backdrop-blur-[4px]"
        icon="dots-vertical"
        icon-stroke-color="base-white"
      >
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="bg-white border border-gray-warm-300 rounded-lg" align="end">
      <DesktopCardHeaderActionsDropdownContent
        :desktop="props.desktop"
        @edit-desktop="emit('editDesktop')"
        @show-delete-modal="emit('showDeleteModal')"
        @show-direct-link-modal="emit('showDirectLinkModal')"
        @show-recreate-modal="emit('showRecreateModal')"
        @create-template="emit('createTemplate')"
        @book-desktop="emit('bookDesktop')"
        @change-image="emit('changeImage')"
        @show-storage-modal="emit('showStorageModal')"
      />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
