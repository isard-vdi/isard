<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalStorage } from '@vueuse/core'

import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupSeparator } from '@/components/ui/button-group'
import { DropdownButton } from '@/components/dropdown-button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const { t } = useI18n()

interface Viewer {
  id: string
  loading: boolean
  // TODO: should you pass loading for each viewer, or should the component manage it based on a global loading prop?
}

// interface Props extends PrimitiveProps {
interface Props {
  viewers: Viewer[]
  selectedViewer?: string
}

const props = withDefaults(defineProps<Props>(), {
  selectedViewer: undefined
})

const emit = defineEmits<{
  openViewer: [id: string]
}>()

const selectedViewer = ref<Viewer>(
  props.viewers.find((v) => v.id === props.selectedViewer) || props.viewers[0]
)

const selectedViewerLabel = computed(() => t(`viewers.${selectedViewer.value.id}`))

const selectedViewerTooltipTitle = computed(() =>
  t(`viewers.tooltip.${selectedViewer.value.id}.title`)
)

const selectedViewerTooltipDescription = computed(() =>
  t(`viewers.tooltip.${selectedViewer.value.id}.description`)
)

const viewerTooltipDismissed = useLocalStorage('viewer-tooltip-dismissed', false)
const tooltipOpen = ref(false)
const dropdownTooltipOpen = ref<Record<string, boolean>>({})

const dismissTooltip = () => {
  tooltipOpen.value = false
  Object.keys(dropdownTooltipOpen.value).forEach((id) => {
    dropdownTooltipOpen.value[id] = false
  })
  viewerTooltipDismissed.value = true
}

const selectViewer = (viewer: Viewer) => {
  // if (viewer.loading) {
  //   return
  // }

  if (viewer.id !== selectedViewer.value.id) {
    selectedViewer.value = viewer
  }

  emit('openViewer', viewer.id)
}
</script>

<template>
  <ButtonGroup class="min-w-0">
    <!-- TODO: rework component to update loading state dynamically -->
    <Tooltip
      :open="tooltipOpen"
      :disabled="viewerTooltipDismissed"
      @update:open="tooltipOpen = $event"
    >
      <TooltipTrigger as-child>
        <Button
          class="min-w-0 overflow-hidden"
          :icon="selectedViewer.loading ? 'loading-02' : ''"
          icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
          :disabled="selectedViewer.loading"
          @click="selectViewer(selectedViewer)"
          ><span class="min-w-0 truncate">{{ selectedViewerLabel }}</span></Button
        >
      </TooltipTrigger>
      <TooltipContent
        :title="selectedViewerTooltipTitle"
        :subtitle="selectedViewerTooltipDescription"
        :dismiss-label="t('viewers.tooltip-dismiss')"
        @dismiss="dismissTooltip"
      />
    </Tooltip>

    <template v-if="props.viewers.length > 1">
      <ButtonGroupSeparator color="brand-800" />

      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button icon="chevron-down" class="rounded-l-none" />
        </DropdownMenuTrigger>
        <DropdownMenuContent class="bg-white border border-[#D7D3D0] rounded-lg" align="end">
          <DropdownMenuGroup>
            <template v-for="viewer in viewers" :key="viewer.id">
              <DropdownMenuItem v-if="viewer.id !== selectedViewer.id">
                <Tooltip
                  :disabled="viewerTooltipDismissed"
                  :open="dropdownTooltipOpen[viewer.id]"
                  @update:open="dropdownTooltipOpen[viewer.id] = $event"
                >
                  <TooltipTrigger as-child>
                    <Button
                      class="mr-2 w-full justify-start"
                      hierarchy="link-gray"
                      :icon="viewer.loading ? 'loading-02' : ''"
                      icon-size="md"
                      icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
                      :disabled="viewer.loading"
                      @click="selectViewer(viewer)"
                    >
                      {{ t(`viewers.${viewer.id}`) }}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent
                    :title="t(`viewers.tooltip.${viewer.id}.title`)"
                    :subtitle="t(`viewers.tooltip.${viewer.id}.description`)"
                    :dismiss-label="t('viewers.tooltip-dismiss')"
                    side="left"
                    @dismiss="dismissTooltip"
                  />
                </Tooltip>
              </DropdownMenuItem>
            </template>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ButtonGroup>
</template>
