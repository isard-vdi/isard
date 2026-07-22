<script setup lang="ts">
import { ref, computed, defineProps, defineEmits, withDefaults } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop } from '@/gen/oas/apiv4/'
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
  DesktopCardNetworksOverlay,
  DesktopCardInfoOverlay,
  DesktopCardBastionOverlay,
  DesktopCardPreview,
  cardOverlayPaddingVariants
} from '.'
import { Icon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { ContextMenuContent, ContextMenuItem } from '@/components/ui/context-menu'

const { t, d } = useI18n()

interface Props {
  desktop: ApiSchemasDomainsDesktopsUserDesktop
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
  changeImage: []
  showStorageModal: []
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

// One overlay at a time — clicking the same icon toggles off, clicking
// another swaps. The expand button inside each overlay opens the matching
// full-screen modal.
type OverlayKind = 'info' | 'networks' | 'bastion'
const activeOverlay = ref<OverlayKind | null>(null)

const toggleOverlay = (kind: OverlayKind) => {
  activeOverlay.value = activeOverlay.value === kind ? null : kind
}

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
    :show-overlay="activeOverlay !== null"
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
        :active-overlay="activeOverlay"
        @info-click="toggleOverlay('info')"
        @network-click="toggleOverlay('networks')"
        @bastion-click="toggleOverlay('bastion')"
        @edit-desktop="emit('editDesktop')"
        @show-delete-modal="emit('showDeleteModal')"
        @show-direct-link-modal="emit('showDirectLinkModal')"
        @show-recreate-modal="emit('showRecreateModal')"
        @create-template="emit('createTemplate')"
        @book-desktop="emit('bookDesktop')"
        @change-image="emit('changeImage')"
        @show-storage-modal="emit('showStorageModal')"
      />
    </template>

    <template #overlay>
      <DesktopCardInfoOverlay
        v-if="activeOverlay === 'info'"
        :desktop="desktop"
        @show-info-modal="emit('showInfoModal')"
      />

      <div
        v-else-if="activeOverlay === 'networks'"
        :class="cardOverlayPaddingVariants({ size: props.size })"
        class="text-base-white text-start"
      >
        <div class="flex items-center gap-2 mb-1.5">
          <Icon name="modem-02" size="sm" stroke-color="base-white" />
          <span class="text-[10px] font-bold uppercase tracking-wide truncate">
            {{ t('components.desktops.desktop-card.actions.networks') }}
          </span>
        </div>
        <DesktopCardNetworksOverlay
          :desktop-id="desktop.id"
          :desktop-status="desktop.status"
          :desktop-ip="desktop.ip"
          :full-height="!(notificationText && desktop.description?.trim().length !== 0)"
          @show-networks-modal="emit('showNetworksModal')"
        />
        <div class="flex justify-end mt-1.5">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="link-gray"
                size="sm"
                class="h-6! px-2! gap-1 bg-base-white/15 hover:bg-base-white/30 text-[10px] font-semibold text-base-white"
                @click="emit('showNetworksModal')"
              >
                {{ t('components.desktops.desktop-card.overlay.expand') }}
                <Icon name="expand-04" size="xs" stroke-color="base-white" />
              </Button>
            </TooltipTrigger>
            <TooltipContent :title="t('components.desktops.desktop-card.overlay.expand-tooltip')" />
          </Tooltip>
        </div>
      </div>

      <DesktopCardBastionOverlay
        v-else-if="activeOverlay === 'bastion'"
        :desktop="desktop"
        @show-bastion-modal="emit('showBastionModal')"
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
