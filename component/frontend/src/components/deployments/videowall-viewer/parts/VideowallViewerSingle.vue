<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, MousePointerClick, Pin } from 'lucide-vue-next'
import { refDebounced } from '@vueuse/core'

import { canViewInBrowser, type VideowallDesktop } from '@/lib/videowall'
import { cn } from '@/lib/utils'
import { useVideowallStream } from '@/composables/useVideowallStream'

import { Icon } from '@/components/icon'
import NoVNC from '@/components/noVNC/NoVNC.vue'
import { Spinner } from '@/components/ui/spinner'

import type { ViewerNotice } from '../constants'

interface Props {
  desktop: VideowallDesktop | null
  viewOnly: boolean
  notice: ViewerNotice | null
  flashing: boolean
}

const props = defineProps<Props>()

const { t } = useI18n()

const NOTICES = {
  view: { icon: Eye, iconClass: '', text: 'views.deployment-videowall.viewer.mode.view-notice' },
  control: {
    icon: MousePointerClick,
    iconClass: 'text-warning-500',
    text: 'views.deployment-videowall.viewer.mode.control-notice'
  },
  pinned: {
    icon: Pin,
    iconClass: 'text-brand-300',
    text: 'views.deployment-videowall.viewer.pinned.notice'
  }
} as const

const watchable = computed(() => props.desktop !== null && canViewInBrowser(props.desktop))
// Stepping fast only connects to where it stops, not to every desktop on the way.
const SETTLE_MS = 300
const desktopId = computed(() => props.desktop?.id ?? null)
const settledId = refDebounced(desktopId, SETTLE_MS)
const { vncValues, connectionKey, connecting, failed, onConnect, onDisconnect } =
  useVideowallStream(
    () => props.desktop,
    () => settledId.value === desktopId.value
  )
const waiting = computed(
  () => watchable.value && (settledId.value !== desktopId.value || connecting.value)
)
</script>

<template>
  <div class="relative min-h-0 flex-1">
    <!-- Keyed on the connection, so stepping or a fresh password reconnects. -->
    <NoVNC
      v-if="vncValues && !failed"
      :key="connectionKey ?? undefined"
      :viewer="vncValues"
      height="100%"
      :view-only="props.viewOnly"
      class="absolute inset-0"
      @first-frame="onConnect"
      @disconnect="onDisconnect"
    />
    <!-- Mode switch feedback; never blocks the desktop's input. -->
    <Transition leave-active-class="transition-opacity duration-700" leave-to-class="opacity-0">
      <div
        v-if="props.flashing && props.notice"
        :class="
          cn(
            'pointer-events-none absolute inset-0 z-10 ring-4 ring-inset',
            props.notice.kind === 'control' ? 'ring-warning-500' : 'ring-gray-warm-100'
          )
        "
      />
    </Transition>
    <Transition
      mode="out-in"
      enter-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-active-class="transition-opacity duration-300"
      leave-to-class="opacity-0"
    >
      <div
        v-if="props.notice"
        :key="props.notice.key"
        role="status"
        class="pointer-events-none absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-gray-warm-900/85 px-4 py-2.5 text-sm font-medium text-base-white shadow-lg"
      >
        <component
          :is="NOTICES[props.notice.kind].icon"
          :class="cn('size-4 shrink-0', NOTICES[props.notice.kind].iconClass)"
        />
        {{ t(NOTICES[props.notice.kind].text) }}
      </div>
    </Transition>
    <div
      v-if="!watchable || failed"
      class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-gray-warm-400"
    >
      <Icon name="monitor-01" size="xxl" stroke-color="gray-warm-500" />
      <p class="text-sm font-medium">
        {{ t('views.view-deployment.sections.viewer.empty.not-available') }}
      </p>
    </div>
    <!-- Matches the noVNC background, so the fade-out shows no flash. -->
    <Transition leave-active-class="transition-opacity duration-300" leave-to-class="opacity-0">
      <div
        v-if="waiting"
        class="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-gray-warm-800"
        aria-live="polite"
      >
        <Spinner />
        <p class="text-sm font-medium text-gray-warm-200">
          {{ t('views.deployment-videowall.viewer.connecting') }}
        </p>
      </div>
    </Transition>
  </div>
</template>
