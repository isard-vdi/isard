<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalStorage } from '@vueuse/core'
import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuPortal,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import { desktopActionsData, DesktopActionsEnum } from '@/lib/desktops'
import { ViewerSelectDropdownItem } from '../viewer-select'

const { t, d } = useI18n()

interface Props {
  desktop: {
    id: string
    name: string
    image: {
      url: string
    }
    status: string
    viewers: string[] // TODO: type this properly
    ip: string | null
    permissions?: string[]
  }
  selected: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: false
})

const emit = defineEmits<{
  select: []
  desktopStop: []
  desktopStart: []
  openViewer: [id: string]

  showInfoModal: []
  showRecreateModal: []
}>()

const mainButtonData = computed(() => {
  return desktopActionsData(props.desktop.status, false)
})

const handleDesktopAction = (action: DesktopActionsEnum) => {
  // TODO: Evaluate addding more complex actions here

  switch (action) {
    case DesktopActionsEnum.Stop:
      emit('desktopStop')
      break
    case DesktopActionsEnum.Start:
      emit('desktopStart')
      break

    default:
      console.log('unimplemented')
      break
  }
}

const desktopViewers = computed(() => {
  return props.desktop.viewers.map((viewer) => viewer.replace(/_/g, '-'))
})

const canOpenViewer = computed(() => {
  return (
    !!mainButtonData.value.viewers &&
    !props.selected &&
    desktopViewers.value.includes('browser-vnc')
  )
})

const openViewer = () => {
  if (canOpenViewer.value) {
    emit('select')
  }
}
const viewerTooltipDismissed = useLocalStorage('viewer-tooltip-dismissed', false)
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
</script>

<template>
  <div
    :class="
      cn(
        selected
          ? 'bg-brand-700 text-base-white'
          : [
              'text-gray-warm-800',
              canOpenViewer
                ? 'cursor-pointer hover:bg-brand-100 pointer-coarse:bg-brand-100'
                : 'cursor-not-allowed hover:bg-gray-warm-100 pointer-coarse:bg-gray-warm-100'
            ],
        'mx-2 p-2 pr-4 rounded-lg flex flex-row items-center justify-center gap-2',
        'transition-colors duration-200 ease-in-out'
      )
    "
    @click="openViewer"
  >
    <div
      class="size-16 shrink-0 bg-cover bg-center rounded-md"
      :style="{
        backgroundImage: `url(${desktop.image.url})`
      }"
    />

    <div class="flex flex-col items-start gap-1 w-full overflow-hidden">
      <p class="line-clamp-1 text-sm font-semibold">
        {{ desktop.name }}
      </p>

      <!-- TODO: inform the user if the desktop doesn't have novnc -->
      <Tooltip>
        <TooltipTrigger as-child>
          <Button
            :disabled="!canOpenViewer"
            hierarchy="link-color"
            class="p-0"
            @click="emit('select')"
            >{{
              props.selected
                ? t('components.deployments.desktop-card.viewing')
                : t('components.deployments.desktop-card.view')
            }}</Button
          >
        </TooltipTrigger>
        <TooltipContent
          v-if="!canOpenViewer"
          :title="t('components.deployments.desktop-card.not-available')"
          side="top"
        />
      </Tooltip>
    </div>

    <div class="ml-auto flex flex-row items-center gap-4">
      <Tooltip v-if="mainButtonData?.actionButton">
        <TooltipTrigger as-child>
          <Button
            :hierarchy="mainButtonData.actionButton.hierarchy"
            :icon="mainButtonData.actionButton.icon"
            :icon-class="mainButtonData.actionButton.iconClass"
            class="shrink-0 p-[10px]"
            :disabled="
              ![DesktopActionsEnum.Start, DesktopActionsEnum.Stop].includes(
                mainButtonData.actionButton.action
              )
            "
            @click.stop="handleDesktopAction(mainButtonData.actionButton.action)"
          />
        </TooltipTrigger>
        <TooltipContent
          :title="
            mainButtonData.actionButton.label
              ? t(mainButtonData.actionButton.label)
              : t(
                  `components.desktops.desktop-card.status.${props.desktop.status.toLowerCase()}.action`
                )
          "
          side="left"
        />
      </Tooltip>

      <div
        v-if="mainButtonData.text"
        class="flex items-center gap-2 ml-auto mr-auto select-none min-w-0 truncate text-xs"
      >
        <Icon
          v-if="mainButtonData.text.icon"
          :name="mainButtonData.text.icon"
          size="md"
          class="shrink-0"
          :class="mainButtonData.text.iconClass"
          :stroke-color="mainButtonData.text.iconColor"
        />
        <template v-if="true">
          {{
            t(`components.desktops.desktop-card.status.${props.desktop.status.toLowerCase()}.text`)
          }}
        </template>
      </div>

      <!-- <ViewerSelect
        v-if="mainButtonData.viewers"
        :viewers="
          props.desktop.viewers?.map((viewer) => ({
            id: viewer.replace(/_/g, '-'),
            loading: viewer.includes('rdp') && !props.desktop.ip
          }))
        "
        selected-viewer="browser-vnc"
        _size="compact"
        @open-viewer="(viewer) => $emit('openViewer', viewer)"
      /> -->

      <DropdownMenu>
        <DropdownMenuTrigger @click.stop>
          <Button hierarchy="secondary-gray" class="p-[10px]" icon="dots-vertical" />
        </DropdownMenuTrigger>
        <DropdownMenuContent class="bg-white border border-gray-warm-300 rounded-lg" align="end">
          <template v-if="mainButtonData.viewers">
            <DropdownMenuGroup>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Button size="sm" class="mr-2 w-full justify-start" hierarchy="link-gray">
                    {{ t('components.deployments.desktop-card.viewers') }}
                  </Button>
                </DropdownMenuSubTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuSubContent class="bg-white border border-gray-warm-300 rounded-lg">
                    <!-- <DropdownMenuItem v-for="viewer in props.desktop.viewers" :key="viewer">
                      <Button size="sm" class="mr-2 w-full justify-start" hierarchy="link-gray">
                        {{ viewer }}
                      </Button>
                    </DropdownMenuItem> -->
                    <ViewerSelectDropdownItem
                      v-for="viewer in desktopViewers"
                      :key="viewer"
                      :viewer="{
                        id: viewer,
                        loading: viewer.includes('rdp') && !props.desktop.ip
                      }"
                      :tooltip-dismissed="viewerTooltipDismissed"
                      @select="emit('openViewer', viewer.replace(/_/g, '-'))"
                      @dismiss-tooltip="viewerTooltipDismissed = true"
                    />
                  </DropdownMenuSubContent>
                </DropdownMenuPortal>
              </DropdownMenuSub>
            </DropdownMenuGroup>

            <DropdownMenuSeparator class="bg-gray-warm-300" />
          </template>

          <DropdownMenuGroup>
            <DropdownMenuItem @click="emit('showInfoModal')">
              <Button
                size="sm"
                class="mr-2 w-full justify-start"
                hierarchy="link-gray"
                icon="info-circle"
                icon-size="md"
              >
                {{ t('components.desktops.desktop-card.actions.info') }}
              </Button>
            </DropdownMenuItem>

            <DropdownMenuItem
              v-if="props.desktop.permissions?.includes('recreate')"
              @click="emit('showRecreateModal')"
            >
              <Button
                size="sm"
                class="mr-2 w-full justify-start"
                hierarchy="link-gray"
                icon="refresh-cw-01"
                icon-size="md"
                icon-classa="motion-safe:animate-[spin_2s_linear_infinite]"
              >
                {{ t('components.desktops.desktop-card.actions.recreate') }}
              </Button>
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </div>
</template>
