<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import {
  desktopActionsData,
  DesktopActionsEnum,
  desktopNeedsBooking as checkDesktopNeedsBooking
} from '@/lib/desktops'

import { Button } from '@/components/ui/button'

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
}>()

const desktopNeedsBooking = computed<boolean>(() => {
  return checkDesktopNeedsBooking(props.desktop)
})

const mainButtonData = computed(() => {
  return desktopActionsData(props.desktop.status, desktopNeedsBooking.value)
})

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
    :hierarchy="mainButtonData.actionButton.hierarchy"
    :icon="mainButtonData.actionButton.icon"
    :icon-class="mainButtonData.actionButton.iconClass"
    class="w-full"
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
