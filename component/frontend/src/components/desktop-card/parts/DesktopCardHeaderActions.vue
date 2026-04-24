<script setup lang="ts">
import type { UserDesktop } from '@/gen/oas/apiv4/'

import { DesktopCardHeaderActionsDropdownContent } from '..'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent
} from '@/components/ui/dropdown-menu'

interface Props {
  desktop: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  networkClick: []
  showNetworksModal: []
  showInfoModal: []
  editDesktop: []
  showDeleteModal: []
  showBastionModal: []
  showDirectLinkModal: []
  showRecreateModal: []
  createTemplate: []
  bookDesktop: []
}>()

function handleNetworkClick() {
  if (window.innerWidth < 640) {
    emit('showNetworksModal')
  } else {
    emit('networkClick')
  }
}
</script>

<template>
  <Button
    hierarchy="link-gray"
    size="sm"
    class="w-9! h-9! flex align-center justify-center bg-base-black/30 hover:bg-base-black/50 p-0! backdrop-blur-[4px]"
    icon="modem-02"
    icon-stroke-color="base-white"
    @click="handleNetworkClick"
  >
  </Button>

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
        @show-info-modal="emit('showInfoModal')"
        @edit-desktop="emit('editDesktop')"
        @show-delete-modal="emit('showDeleteModal')"
        @show-bastion-modal="emit('showBastionModal')"
        @show-direct-link-modal="emit('showDirectLinkModal')"
        @show-recreate-modal="emit('showRecreateModal')"
        @create-template="emit('createTemplate')"
        @book-desktop="emit('bookDesktop')"
      />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
