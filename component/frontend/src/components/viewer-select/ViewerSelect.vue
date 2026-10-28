<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalStorage } from '@vueuse/core'
import { cn } from '@/lib/utils'

import { Button, type ButtonVariants } from '@/components/ui/button'
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
import { Icon } from '@/components/icon'
import { toast } from '@/components/ui/toast'
import { type Viewer, ViewerSelectDropdownItem } from '.'

const { t } = useI18n()

// interface Props extends PrimitiveProps {
interface Props {
  viewers: Viewer[]
  selectedViewer?: string
  size?: 'default' | 'compact'
  buttonSize?: ButtonVariants['size']
  // `dense` shrinks the group to the height and type of a table row, and makes
  // it fill its column so every row's group is the same size
  dense?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedViewer: undefined,
  size: 'default',
  buttonSize: 'md',
  dense: false
})

const emit = defineEmits<{
  openViewer: [id: string]
}>()

// Track the selected viewer by id only, then derive the full Viewer object
// from props.viewers each render. Holding a Viewer ref captured once at setup
// time would freeze the loading flag — when props.viewers later flips a
// viewer's loading from true to false (e.g. when desktop.ip arrives via WS),
// the dropdown would keep showing the stale loading=true state and the button
// would stay disabled. Re-derive via computed so the loading flag follows the
// latest props.viewers.
const selectedViewerId = ref<string>(
  (props.viewers.find((v) => v.id === props.selectedViewer) || props.viewers[0])?.id
)

const selectedViewer = computed<Viewer>(
  () => props.viewers.find((v) => v.id === selectedViewerId.value) || props.viewers[0]
)

const selectedViewerLabel = computed(() =>
  selectedViewer.value ? t(`viewers.${selectedViewer.value.id}`) : ''
)

const selectedViewerTooltipTitle = computed(() =>
  selectedViewer.value ? t(`viewers.tooltip.${selectedViewer.value.id}.title`) : ''
)

const selectedViewerTooltipDescription = computed(() =>
  selectedViewer.value ? t(`viewers.tooltip.${selectedViewer.value.id}.description`) : ''
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

// A refused guest shows a warning, not a spinner: waiting won't fix it.
const viewerIcon = (viewer: Viewer) => {
  if (viewer.tone === 'error') return 'alert-circle'
  if (viewer.tone === 'warn') return 'alert-triangle'
  if (viewer.loading) return 'loading-02'
  return ''
}

// A selected RDP viewer's error is shown below the button; a warning is only the triangle, its text on hover.
const outsideNotice = computed(
  () =>
    props.size !== 'compact' &&
    !!selectedViewer.value?.id.includes('rdp') &&
    !!selectedViewer.value.status &&
    selectedViewer.value.tone === 'error'
)

// The RDP readiness tone keys the left-to-right background fill.
const progressTone = (viewer: Viewer) => `viewer-progress--${viewer.tone || 'wait'}`

const selectViewer = (viewer: Viewer) => {
  // A blocked viewer with a status stays tappable so touch screens, where the
  // tooltip never opens, still get told why it can't be opened yet.
  if (viewer.loading) {
    if (viewer.status) toast.info(viewer.status)
    return
  }

  if (viewer.id !== selectedViewerId.value) {
    selectedViewerId.value = viewer.id
  }

  emit('openViewer', viewer.id)
}
</script>

<template>
  <div
    v-if="selectedViewer"
    :class="cn('flex min-w-0 flex-col items-end gap-1', props.dense && 'w-full items-stretch')"
  >
    <ButtonGroup :class="cn('min-w-0', props.dense && 'w-full')">
      <!-- TODO: rework component to update loading state dynamically -->
      <Tooltip
        v-if="props.size !== 'compact'"
        :open="tooltipOpen"
        :disabled="viewerTooltipDismissed && (!selectedViewer.status || outsideNotice)"
        @update:open="tooltipOpen = $event"
      >
        <TooltipTrigger as-child>
          <Button
            :class="
              cn(
                'relative isolate min-w-0 overflow-hidden',
                props.dense && 'h-7 flex-1 gap-1 px-2 py-0 text-xs',
                selectedViewer.loading && selectedViewer.status && 'opacity-60 cursor-not-allowed'
              )
            "
            :size="props.buttonSize"
            :icon="selectedViewer.tone === 'warn' ? '' : viewerIcon(selectedViewer)"
            :icon-stroke-color="selectedViewer.tone === 'error' ? 'error-600' : undefined"
            :icon-size="props.dense ? 'xs' : undefined"
            :icon-class="
              cn(
                'relative z-10',
                selectedViewer.loading &&
                  selectedViewer.tone !== 'error' &&
                  selectedViewer.tone !== 'warn' &&
                  'motion-safe:animate-[spin_2s_linear_infinite]'
              )
            "
            :disabled="selectedViewer.loading && !selectedViewer.status"
            :aria-disabled="selectedViewer.loading ? 'true' : undefined"
            :data-viewer-status="
              selectedViewer.status && !outsideNotice ? selectedViewer.tone || 'info' : undefined
            "
            @click="selectViewer(selectedViewer)"
            ><span
              v-if="selectedViewer.progress !== undefined"
              class="viewer-progress"
              :class="progressTone(selectedViewer)"
              :style="{ width: selectedViewer.progress + '%' }"
              role="progressbar"
              :aria-valuenow="selectedViewer.progress"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuetext="selectedViewer.status"
              :aria-label="selectedViewer.status" /><span class="relative z-10 min-w-0 truncate">{{
              selectedViewerLabel
            }}</span
            ><Icon
              v-if="selectedViewer.tone === 'warn'"
              name="alert-triangle"
              :size="props.dense ? 'xs' : undefined"
              stroke-color="warning-600"
              class="relative z-10 shrink-0"
          /></Button>
        </TooltipTrigger>
        <TooltipContent
          v-if="selectedViewer.status && !outsideNotice"
          :title="selectedViewer.status"
          data-testid="viewer-status-tooltip"
        />
        <TooltipContent
          v-else
          :title="selectedViewerTooltipTitle"
          :subtitle="selectedViewerTooltipDescription"
          :dismiss-label="t('viewers.tooltip-dismiss')"
          @dismiss="dismissTooltip"
        />
      </Tooltip>

      <template v-if="props.viewers.length > 1">
        <ButtonGroupSeparator v-if="props.size !== 'compact'" color="brand-800" />

        <DropdownMenu>
          <DropdownMenuTrigger @click.stop>
            <Button
              :aria-label="t('common.actions.other-viewers')"
              icon="chevron-down"
              :size="props.buttonSize"
              :icon-size="props.dense ? 'sm' : undefined"
              :class="
                cn(
                  props.size === 'compact' ? 'p-[10px]' : 'rounded-l-none px-2',
                  props.dense && 'h-7 shrink-0 px-1.5 py-0'
                )
              "
            />
          </DropdownMenuTrigger>
          <DropdownMenuContent class="bg-white border border-[#D7D3D0] rounded-lg" align="end">
            <DropdownMenuGroup>
              <template v-for="viewer in viewers" :key="viewer.id">
                <!-- <DropdownMenuItem v-if="viewer.id !== selectedViewer.id">
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
              </DropdownMenuItem> -->
                <ViewerSelectDropdownItem
                  v-if="viewer.id !== selectedViewer.id"
                  :viewer="viewer"
                  :tooltip-dismissed="viewerTooltipDismissed"
                  @select="selectViewer(viewer)"
                  @dismiss-tooltip="dismissTooltip"
                />
              </template>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </template>
    </ButtonGroup>
    <Tooltip v-if="outsideNotice">
      <TooltipTrigger as-child>
        <p
          :class="
            cn(
              'flex w-0 min-w-full items-center gap-1 text-xs',
              selectedViewer.tone === 'error' ? 'text-error-700' : 'text-warning-800'
            )
          "
          role="status"
          :data-viewer-status="selectedViewer.tone"
          data-testid="viewer-status-notice"
        >
          <Icon
            :name="selectedViewer.tone === 'error' ? 'alert-circle' : 'alert-triangle'"
            size="xs"
            stroke-color=""
            class="shrink-0"
          /><span class="min-w-0 truncate">{{ selectedViewer.status }}</span>
        </p>
      </TooltipTrigger>
      <TooltipContent :title="selectedViewer.status" />
    </Tooltip>
  </div>
</template>

<style scoped>
/* Left-to-right readiness fill behind the viewer label. Tone colours are
   translucent so they read on the button's own background in both themes. */
.viewer-progress {
  position: absolute;
  inset: 0 auto 0 0;
  z-index: 0;
  pointer-events: none;
  border-radius: inherit;
  transition: width 0.3s ease;
}
.viewer-progress--wait {
  background-color: rgba(56, 189, 248, 0.4);
}
.viewer-progress--warn {
  background-color: rgba(251, 191, 36, 0.45);
}
.viewer-progress--error {
  background-color: rgba(248, 113, 113, 0.42);
}
.viewer-progress--info {
  background-color: rgba(56, 189, 248, 0.4);
}
</style>
