<script setup lang="ts">
import { ref, computed, defineProps, defineEmits, withDefaults } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4/'
import type { CardSize } from '.'

import { cn, copyToClipboard } from '@/lib/utils'
import {
  desktopActionsData,
  DesktopActionsEnum,
  desktopNotificationText,
  desktopNeedsBooking as checkDesktopNeedsBooking
} from '@/lib/desktops'

import {
  DesktopCardBase,
  DesktopCardFooter,
  DesktopCardHeader,
  DesktopCardHeaderActions,
  DesktopCardIp,
  DesktopCardNetworksOverlay,
  DesktopCardPreview
} from '.'
import { ContextMenuContent, ContextMenuItem } from '@/components/ui/context-menu'

const { t, d } = useI18n()

interface Props {
  desktop: UserDesktop
  preferredViewer?: string
  blank?: boolean
  size?: CardSize
  fill?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  preferredViewer: undefined,
  blank: false,
  size: 'md',
  fill: false
})

const emit = defineEmits<{
  // --- Main actions ---
  desktopStart: []
  desktopStop: []
  desktopUpdateStatus: []
  desktopAbortOperation: []
  desktopFetchBooking: []
  // desktop*: []
  // --- Viewers ---
  openViewer: [viewer: string]
  // --- Modals ---
  fetchNetworks: []
  showNetworksModal: []
  showInfoModal: []
  showBastionModal: []
  showDirectLinkModal: []
  showDeleteModal: []
  showRecreateModal: []
  // show*Modal: []
  // --- Redirects ---
  editDesktop: []
  bookDesktop: []
  createTemplate: []
  // goTo*: []
}>()

const handleDesktopAction = (action: DesktopActionsEnum) => {
  // TODO: probably could just emit(action) directly, but typescript complains

  switch (action) {
    case DesktopActionsEnum.Stop:
      emit('desktopStop')
      break
    case DesktopActionsEnum.Start:
      emit('desktopStart')
      break
    case DesktopActionsEnum.AbortOperation:
      emit('desktopAbortOperation')
      break
    case DesktopActionsEnum.UpdateStatus:
      emit('desktopUpdateStatus')
      break
    case DesktopActionsEnum.FetchBooking:
      emit('desktopFetchBooking')
      break
  }
}

const desktopNeedsBooking = computed<boolean>(() => {
  return checkDesktopNeedsBooking(props.desktop)
})

const mainButtonData = computed(() => {
  return desktopActionsData(props.desktop.status, desktopNeedsBooking.value)
})

const notificationText = computed<string | null>(() => {
  return desktopNotificationText(props.desktop, t, d)
})

const showNetworkOverlay = ref<boolean>(false)

const desktopKind = computed(() => {
  if (props.desktop.tag) {
    return 'deployment'
  }

  return props.desktop.type as 'persistent' | 'nonpersistent'
})
</script>

<template>
  <DesktopCardBase
    v-bind="props"
    :show-network-overlay="showNetworkOverlay"
    :desktop-kind="desktopKind"
    :image-url="props.desktop.image?.url ?? ''"
  >
    <template #image>
      <DesktopCardPreview
        :desktop="desktop"
        :image-url="props.desktop.image?.url ?? ''"
        :size="props.size"
      />
    </template>

    <template #debug-options-content>
      <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
        <ContextMenuItem @click="copyToClipboard(props.desktop.id)">{{
          t('components.desktops.desktop-card.debug-options.copy-id')
        }}</ContextMenuItem>
      </ContextMenuContent>
    </template>

    <template #header-actions>
      <DesktopCardHeaderActions
        :desktop="desktop"
        @network-click="showNetworkOverlay = !showNetworkOverlay"
        @show-networks-modal="emit('showNetworksModal')"
        @show-info-modal="emit('showInfoModal')"
        @edit-desktop="emit('editDesktop')"
        @show-delete-modal="emit('showDeleteModal')"
        @show-bastion-modal="emit('showBastionModal')"
        @show-direct-link-modal="emit('showDirectLinkModal')"
        @show-recreate-modal="emit('showRecreateModal')"
        @create-template="emit('createTemplate')"
        @book-desktop="emit('bookDesktop')"
      />
    </template>

    <template #ip>
      <DesktopCardIp
        v-if="desktop.interfaces.find((iface) => iface.id === 'wireguard')"
        :desktop-status="desktop.status"
        :desktop-ip="desktop.ip"
      />
    </template>
    <template #networks>
      <!-- TODO: this should probably be in the view, as it contains an api call -->
      <DesktopCardNetworksOverlay
        :desktop-id="desktop.id"
        :full-height="!(notificationText && desktop.description?.trim().length !== 0)"
        @show-networks-modal="emit('showNetworksModal')"
      />
    </template>

    <template #header>
      <DesktopCardHeader
        :notification-text="notificationText"
        :name="desktop.name"
        :description="desktop.description || ''"
        :download-progress="
          desktop.progress && desktop.progress.percentage !== undefined
            ? desktop.progress
            : undefined
        "
      />
    </template>

    <template #footer>
      <DesktopCardFooter
        :main-button-data="mainButtonData"
        :desktop-status="desktop.status"
        :desktop-viewers="desktop.viewers"
        :preferred-viewer="preferredViewer"
        :desktop-ip="desktop.ip"
        @main-button-click="handleDesktopAction(mainButtonData.actionButton!.action)"
        @open-viewer="(viewer) => emit('openViewer', viewer)"
      />
    </template>
  </DesktopCardBase>
</template>
