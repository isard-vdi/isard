<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import {
  desktopActionsData,
  DesktopActionsEnum,
  desktopNeedsBooking as checkDesktopNeedsBooking
} from '@/lib/desktops'

import { Button, type ButtonVariants } from '@/components/ui/button'

const { t } = useI18n()

interface Props {
  desktop: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  // --- Main actions ---
  desktopStart: []
  desktopStop: []
  desktopUpdateStatus: []
  desktopAbortOperation: []
  desktopFetchBooking: []
  // --- Modals ---
  showDeleteModal: []
}>()

const desktopNeedsBooking = computed<boolean>(() => {
  return checkDesktopNeedsBooking(props.desktop)
})

const mainButtonData = computed(() => {
  return desktopActionsData(
    props.desktop.status,
    desktopNeedsBooking.value,
    false,
    props.desktop.type !== 'nonpersistent'
  )
})

const buttonHierarchy = computed(
  () => mainButtonData.value.actionButton?.hierarchy as ButtonVariants['hierarchy']
)

const handleDesktopAction = (action: DesktopActionsEnum) => {
  // TODO: probably could just emit(action) directly, but typescript complains

  switch (action) {
    case DesktopActionsEnum.Stop:
      emit('desktopStop')
      break
    case DesktopActionsEnum.Start:
      emit('desktopStart')
      break
    case DesktopActionsEnum.Delete:
      emit('showDeleteModal')
      break
    case DesktopActionsEnum.AbortOperation:
      emit('desktopAbortOperation')
      break
    case DesktopActionsEnum.UpdateStatus:
      emit('desktopUpdateStatus')
      break
    // case DesktopActionsEnum.StartNow:
    //   emit('showStartNowModal')
    //   break
    case DesktopActionsEnum.FetchBooking:
      emit('desktopFetchBooking')
      break
  }
}
</script>

<template>
  <!-- <template
    v-for="mainButtonData in [
      desktopActionsData(row.status, /* desktopNeedsBooking.value */ false)
    ]"
    :key="mainButtonData.actionButton"
  >
</template> -->
  <Button
    v-if="mainButtonData.actionButton"
    :key="mainButtonData.actionButton.action"
    :hierarchy="buttonHierarchy"
    :icon="mainButtonData.actionButton.icon"
    :icon-class="mainButtonData.actionButton.iconClass"
    icon-size="xs"
    size="sm"
    class="h-7 w-full gap-1 px-2 py-0 text-xs transition-none motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300"
    @click="handleDesktopAction(mainButtonData.actionButton.action)"
  >
    {{
      mainButtonData.actionButton.label
        ? t(mainButtonData.actionButton.label)
        : t(
            `components.desktops.desktop-card.status.${props.desktop.status.toLowerCase()}.action`
            // t(`components.desktops.desktop-card.status.unknown.text`)
          )
    }}
  </Button>
</template>
