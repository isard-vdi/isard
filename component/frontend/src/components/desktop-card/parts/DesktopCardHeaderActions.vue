<script setup lang="ts">
import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4/'

import { DesktopCardHeaderActionsDropdownContent, DesktopCardOverlayButton } from '..'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent
} from '@/components/ui/dropdown-menu'

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
</script>

<template>
  <DesktopCardOverlayButton
    icon="info-circle"
    title="components.desktops.desktop-card.actions.info"
    :active="props.activeOverlay === 'info'"
    @click="emit('infoClick')"
  />

  <DesktopCardOverlayButton
    icon="modem-02"
    title="components.desktops.desktop-card.actions.networks"
    :active="props.activeOverlay === 'networks'"
    @click="emit('networkClick')"
  />

  <DesktopCardOverlayButton
    v-if="bastionEnabled"
    icon="globe-04"
    title="components.desktops.desktop-card.actions.bastion-access"
    active-label="components.desktops.desktop-card.actions.bastion"
    aria-label="components.desktops.desktop-card.actions.bastion-access"
    :active="props.activeOverlay === 'bastion'"
    @click="emit('bastionClick')"
  />

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
