<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEventListener, useFullscreen, useLocalStorage } from '@vueuse/core'

import { canViewInBrowser, type VideowallDesktop } from '@/lib/videowall'
import { cn } from '@/lib/utils'

import { AvatarLabel } from '@/components/avatar-label'
import { Icon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { TruncatedText } from '@/components/truncated-text'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import VideowallViewerDensityToggle from './parts/VideowallViewerDensityToggle.vue'
import VideowallViewerModeToggle from './parts/VideowallViewerModeToggle.vue'
import VideowallViewerMosaic from './parts/VideowallViewerMosaic.vue'
import VideowallViewerPicker from './parts/VideowallViewerPicker.vue'
import VideowallViewerPinnedSidebar from './parts/VideowallViewerPinnedSidebar.vue'
import VideowallViewerSingle from './parts/VideowallViewerSingle.vue'
import VideowallViewerSingleActions from './parts/VideowallViewerSingleActions.vue'
import {
  AVATAR_LABEL_TRUNCATE,
  BAR_BUTTON,
  MAX_PINNED,
  type ViewerNotice,
  type MosaicDensity,
  type ViewerLayout,
  type ViewerMode
} from './constants'

interface Props {
  /** The wall as it is shown, so stepping follows its grouping and filters. */
  desktops: VideowallDesktop[]
  deploymentName: string
  /** The whole wall before filtering. */
  total: number
  filterSummary: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{ clearFilters: [] }>()

const desktopId = defineModel<string | null>({ required: true })
const layout = defineModel<ViewerLayout>('layout', { default: 'single' })
const open = computed(() => desktopId.value !== null || layout.value === 'mosaic')

const { t } = useI18n()

const desktop = computed(() => props.desktops.find((d) => d.id === desktopId.value) ?? null)

// Watchable ones, plus the open one even after it stops.
const steps = computed(() =>
  props.desktops.filter((d) => canViewInBrowser(d) || d.id === desktopId.value)
)
const position = computed(() => steps.value.findIndex((d) => d.id === desktopId.value))
const step = (offset: number) => {
  const next = steps.value[position.value + offset]
  if (next) desktopId.value = next.id
}

const openSingle = (id: string) => {
  desktopId.value = id
  layout.value = 'single'
}

// View-only by default: taking over a user's desktop must be a choice.
const mode = useLocalStorage<ViewerMode>('videowall-viewer-mode', 'view')
const watchOnly = computed(() => mode.value === 'view' || layout.value === 'mosaic')

// Mode and pin changes are invisible otherwise; a mode switch also flashes the frame.
const NOTICE_MS = 2000
const FLASH_MS = 150
const notice = ref<ViewerNotice | null>(null)
const flashing = ref(false)
let noticeTimer: ReturnType<typeof setTimeout> | undefined
let flashTimer: ReturnType<typeof setTimeout> | undefined
const clearNotice = () => {
  clearTimeout(noticeTimer)
  clearTimeout(flashTimer)
  notice.value = null
  flashing.value = false
}
const announce = (kind: ViewerNotice['kind'], flash: boolean) => {
  clearNotice()
  notice.value = { kind, key: Date.now() }
  noticeTimer = setTimeout(() => (notice.value = null), NOTICE_MS)
  if (!flash) return
  flashing.value = true
  flashTimer = setTimeout(() => (flashing.value = false), FLASH_MS)
}
const setMode = (value: ViewerMode) => {
  mode.value = value
  announce(value, true)
}

const canSingle = computed(() => desktopId.value !== null || steps.value.length > 0)
const layoutSwitch = computed(() =>
  layout.value === 'single'
    ? {
        icon: 'grid-01',
        text: t('views.deployment-videowall.viewer.layout.mosaic'),
        label: t('views.deployment-videowall.viewer.layout.to-mosaic')
      }
    : {
        icon: 'monitor-01',
        text: t('views.deployment-videowall.viewer.layout.single'),
        label: t('views.deployment-videowall.viewer.layout.to-single')
      }
)
const switchLayout = () => {
  if (layout.value === 'single') {
    layout.value = 'mosaic'
    return
  }
  const id = desktopId.value ?? steps.value[0]?.id
  if (id) openSingle(id)
}

const density = useLocalStorage<MosaicDensity>('videowall-mosaic-density', 'md')

const pinnedIds = ref<string[]>([])
const pinned = computed(() =>
  pinnedIds.value
    .map((id) => props.desktops.find((d) => d.id === id))
    .filter((d): d is VideowallDesktop => d !== undefined)
)
const sidebarOpen = ref(true)
const isPinned = computed(
  () => desktopId.value !== null && pinnedIds.value.includes(desktopId.value)
)
const pinFull = computed(() => !isPinned.value && pinnedIds.value.length >= MAX_PINNED)
const togglePin = () => {
  if (!desktopId.value) return
  if (isPinned.value) return unpin(desktopId.value)
  if (pinFull.value) return
  pinnedIds.value = [...pinnedIds.value, desktopId.value]
  sidebarOpen.value = true
  announce('pinned', false)
}
const unpin = (id: string) => {
  pinnedIds.value = pinnedIds.value.filter((pinnedId) => pinnedId !== id)
}

// In control mode the arrows belong to the desktop.
const IGNORE_KEYS_IN = 'input, textarea, [role="listbox"], [role="group"]'
useEventListener(document, 'keydown', (event: KeyboardEvent) => {
  if (!open.value || !watchOnly.value || layout.value !== 'single') return
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if ((event.target as HTMLElement | null)?.closest(IGNORE_KEYS_IN)) return
  const offset = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
  if (!offset) return
  event.preventDefault()
  step(offset)
})

// Fullscreen the page, not the dialog: tooltips and the picker render outside it.
const {
  isSupported: canFullscreen,
  isFullscreen,
  toggle: toggleFullscreen,
  exit: exitFullscreen
} = useFullscreen()
const fullscreenLabel = computed(() =>
  isFullscreen.value
    ? t('views.deployment-videowall.viewer.fullscreen.exit')
    : t('views.deployment-videowall.viewer.fullscreen.enter')
)

onBeforeUnmount(() => {
  clearNotice()
  if (isFullscreen.value) exitFullscreen()
})

const close = () => {
  desktopId.value = null
  layout.value = 'single'
  clearNotice()
  if (isFullscreen.value) exitFullscreen()
}
</script>

<template>
  <Dialog :open="open" @update:open="(isOpen) => !isOpen && close()">
    <!-- While controlling, Escape and outside clicks must not close it. -->
    <DialogContent
      :class="
        cn(
          'flex max-w-none flex-col gap-0 overflow-hidden border-0 bg-gray-warm-900 p-0',
          isFullscreen ? 'h-dvh w-dvw sm:rounded-none' : 'h-[92vh] w-[96vw]'
        )
      "
      @escape-key-down="(event: KeyboardEvent) => !watchOnly && event.preventDefault()"
      @pointer-down-outside="(event: Event) => !watchOnly && event.preventDefault()"
    >
      <header
        class="grid h-16 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b border-gray-warm-200 bg-base-white px-4"
      >
        <DialogTitle class="sr-only">
          {{ layout === 'mosaic' ? props.deploymentName : desktop?.user_name }}
        </DialogTitle>
        <DialogDescription class="sr-only">
          {{
            layout === 'mosaic'
              ? t('views.deployment-videowall.viewer.mosaic.title', props.desktops.length)
              : desktop?.name
          }}
        </DialogDescription>

        <div class="flex min-w-0 items-center justify-start gap-3">
          <VideowallViewerPicker
            v-if="layout === 'mosaic' ? steps.length > 0 : steps.length > 1"
            :desktops="steps"
            :selected-id="layout === 'single' ? desktopId : null"
            @pick="openSingle"
          />
          <VideowallViewerModeToggle :mode="mode" :locked="layout === 'mosaic'" @change="setMode" />
        </div>

        <div class="flex min-w-0 items-center justify-center gap-3">
          <div v-if="layout === 'mosaic'" class="flex min-w-0 max-w-[35vw] items-center gap-3">
            <span
              class="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-secondary-2-100"
            >
              <Icon name="layout-alt-04" size="md" stroke-color="secondary-2-600" />
            </span>
            <span class="flex min-w-0 flex-col">
              <TruncatedText
                as="span"
                :title="props.deploymentName"
                class="block text-md font-semibold text-gray-warm-900"
              />
              <span class="text-sm text-gray-warm-500">
                {{ t('views.deployment-videowall.viewer.mosaic.title', props.desktops.length) }}
              </span>
            </span>
          </div>
          <div v-else-if="desktop" class="flex min-w-0 max-w-[35vw]">
            <AvatarLabel
              :src="desktop.user_photo"
              :name="desktop.user_name"
              size="md"
              name-class="text-md text-gray-warm-900"
              :class="AVATAR_LABEL_TRUNCATE"
            >
              <template #name>
                <TruncatedText as="span" :title="desktop.user_name" class="block" />
              </template>
              <template #sub>
                <span class="flex min-w-0 items-center gap-1.5 text-gray-warm-500">
                  <Icon name="monitor" size="sm" stroke-color="gray-warm-500" class="shrink-0" />
                  <TruncatedText as="span" :title="desktop.name" />
                  <span
                    v-if="isPinned"
                    class="flex shrink-0 items-center gap-1 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700"
                  >
                    <Icon name="pin-02" size="xs" stroke-color="brand-700" />
                    {{ t('views.deployment-videowall.viewer.pinned.badge') }}
                  </span>
                </span>
              </template>
            </AvatarLabel>
          </div>
        </div>

        <div class="flex items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger as-child>
              <!-- A disabled button gets no pointer events: the span keeps the tooltip. -->
              <span class="inline-flex">
                <Button
                  hierarchy="secondary-gray"
                  :icon="layoutSwitch.icon"
                  :disabled="layout === 'mosaic' && !canSingle"
                  @click="switchLayout"
                >
                  {{ layoutSwitch.text }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent :title="layoutSwitch.label" />
          </Tooltip>
          <div class="mx-2 h-6 w-px bg-gray-warm-200" />
          <VideowallViewerDensityToggle v-if="layout === 'mosaic'" v-model="density" />
          <VideowallViewerSingleActions
            v-else
            :pinned="isPinned"
            :pin-full="pinFull"
            :position="position"
            :total="steps.length"
            :shortcuts="watchOnly"
            @pin="togglePin"
            @step="step"
          />
          <div class="mx-2 h-6 w-px bg-gray-warm-200" />
          <Tooltip v-if="canFullscreen">
            <TooltipTrigger as-child>
              <button
                type="button"
                :class="BAR_BUTTON"
                :aria-label="fullscreenLabel"
                :aria-pressed="isFullscreen"
                @click="toggleFullscreen"
              >
                <Icon
                  :name="isFullscreen ? 'minimize-01' : 'maximize-01'"
                  size="lg"
                  stroke-color="gray-warm-600"
                />
              </button>
            </TooltipTrigger>
            <TooltipContent :title="fullscreenLabel" />
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <button
                type="button"
                :class="BAR_BUTTON"
                :aria-label="t('views.view-deployment.sections.viewer.actions.close')"
                @click="close"
              >
                <Icon name="x" size="lg" stroke-color="gray-warm-600" />
              </button>
            </TooltipTrigger>
            <TooltipContent :title="t('views.view-deployment.sections.viewer.actions.close')" />
          </Tooltip>
        </div>
      </header>
      <div
        v-if="layout === 'single' || props.filterSummary"
        :class="
          cn(
            'flex shrink-0 items-center gap-3 bg-base-background px-4 py-2 text-sm',
            layout === 'single' && 'shadow-[inset_4px_0_0_var(--secondary-2-500)]'
          )
        "
      >
        <span v-if="layout === 'single'" class="flex min-w-0 max-w-96 items-center gap-1.5">
          <span
            class="flex size-6 shrink-0 items-center justify-center rounded-md bg-secondary-2-100"
          >
            <Icon name="layout-alt-04" size="xs" stroke-color="secondary-2-600" />
          </span>
          <TruncatedText
            as="span"
            :title="props.deploymentName"
            class="font-semibold text-gray-warm-900"
          />
        </span>
        <template v-if="props.filterSummary">
          <span v-if="layout === 'single'" class="h-4 w-px shrink-0 bg-gray-warm-300" />
          <div class="flex gap-1.5 items-center bg-brand-100 rounded-md px-1.5 py-1">
            <Icon name="filter-funnel-02" size="sm" stroke-color="brand-700" class="shrink-0" />
            <span class="shrink-0 font-semibold text-brand-700">
              {{ t('views.deployment-videowall.viewer.filtered.label') }}
            </span>
          </div>
          <TruncatedText
            as="span"
            :title="props.filterSummary"
            class="min-w-0 font-semibold text-gray-warm-900"
          />
          <span class="shrink-0 text-gray-warm-500">
            ({{
              t('views.deployment-videowall.viewer.filtered.showing', {
                shown: props.desktops.length,
                total: props.total
              })
            }})
          </span>
          <button
            type="button"
            class="ml-auto shrink-0 cursor-pointer rounded-md px-2 py-1 font-semibold text-gray-warm-900 outline-hidden hover:bg-gray-warm-200 focus-visible:ring-3 focus-visible:ring-gray"
            @click="emit('clearFilters')"
          >
            {{ t('views.deployment-videowall.viewer.filtered.clear') }}
          </button>
        </template>
      </div>

      <VideowallViewerMosaic
        v-if="layout === 'mosaic'"
        :desktops="props.desktops"
        :density="density"
        @select="openSingle"
      />
      <div v-else class="flex min-h-0 flex-1">
        <VideowallViewerSingle
          :desktop="desktop"
          :view-only="mode === 'view'"
          :notice="notice"
          :flashing="flashing"
        />
        <VideowallViewerPinnedSidebar
          v-if="pinned.length > 0"
          v-model:open="sidebarOpen"
          :pinned="pinned"
          :on-screen-id="desktopId"
          @select="(id) => (desktopId = id)"
          @unpin="unpin"
        />
      </div>
    </DialogContent>
  </Dialog>
</template>
