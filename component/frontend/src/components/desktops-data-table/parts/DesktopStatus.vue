<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4'

import { desktopActionsData, desktopNeedsBooking } from '@/lib/desktops'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { Icon, CopyIcon } from '@/components/icon'

import { startCase } from '@/lib/utils'

const { t } = useI18n()

interface Props {
  desktop: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {})

const mainButtonData = computed(() => {
  return desktopActionsData(props.desktop.status, desktopNeedsBooking(props.desktop))
})
</script>

<template>
  <div
    v-if="mainButtonData.text"
    class="flex items-center gap-2 text-sm ml-auto mr-auto select-none font-semibold"
  >
    <Icon
      v-if="mainButtonData.text.icon"
      :name="mainButtonData.text.icon"
      size="md"
      class="shrink-0"
      :class="mainButtonData.text.iconClass"
      :stroke-color="mainButtonData.text.iconColor"
    />
    {{
      t(
        `components.desktops.desktop-card.status.${props.desktop.status.toLowerCase()}.text`
        // t(`components.desktops.desktop-card.status.unknown.text`)
      )
    }}
  </div>
  <div v-else class="flex flex-col items-start justify-start w-full gap-2">
    <div class="text-sm select-none flex flex-row font-semibold">
      {{
        t(
          `components.desktops.desktop-card.status.${props.desktop.status.toLowerCase()}.text`
          // t(`components.desktops.desktop-card.status.unknown.text`)
        )
      }}
    </div>
    <div
      v-if="props.desktop.ip"
      class="flex flex-row items-center gap-1 text-muted-foreground text-xs"
    >
      <Tooltip>
        <TooltipTrigger as-child>
          <p>{{ props.desktop.ip }}</p>
        </TooltipTrigger>
        <TooltipContent :title="startCase(t(`components.desktops.fields.ip.title-full`))">
        </TooltipContent>
      </Tooltip>

      <CopyIcon :value="props.desktop.ip" size="xs" stroke-color="currentColor" />
    </div>
  </div>
</template>
