<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { VideowallDesktop } from '@/lib/videowall'
import { cn } from '@/lib/utils'
import { useVideowallStream } from '@/composables/useVideowallStream'

import { Icon } from '@/components/icon'
import { TruncatedText } from '@/components/truncated-text'
import NoVNC from '@/components/noVNC/NoVNC.vue'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface Props {
  desktop: VideowallDesktop
  /** Already in the main viewer: no second connection to it. */
  onScreen: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{ select: []; unpin: [] }>()

const { t } = useI18n()

const { streaming, vncValues, connectionKey, connecting, failed, onConnect, onDisconnect } =
  useVideowallStream(
    () => props.desktop,
    () => !props.onScreen
  )
</script>

<template>
  <div class="group relative">
    <button
      type="button"
      :class="
        cn(
          'flex w-full cursor-pointer flex-col gap-1.5 rounded-md p-1.5 text-left outline-hidden hover:bg-gray-warm-100 focus-visible:ring-3 focus-visible:ring-gray',
          props.onScreen && 'bg-gray-warm-100'
        )
      "
      :disabled="props.onScreen"
      @click="emit('select')"
    >
      <div
        :class="
          cn(
            'relative aspect-video w-full overflow-hidden rounded-sm bg-gray-warm-800 ring-1 ring-gray-warm-200',
            props.onScreen && 'ring-2 ring-brand'
          )
        "
      >
        <NoVNC
          v-if="vncValues && !failed"
          :key="connectionKey ?? undefined"
          :viewer="vncValues"
          height="100%"
          view-only
          :quality-level="0"
          :compression-level="9"
          background="transparent"
          @first-frame="onConnect"
          @disconnect="onDisconnect"
        />
        <!-- Deployment tint: on screen, not unavailable. -->
        <span
          v-if="props.onScreen"
          class="absolute inset-0 flex items-center justify-center gap-1.5 bg-secondary-2-100 px-2 text-center text-xs font-semibold text-secondary-2-600"
        >
          <Icon name="eye" size="sm" stroke-color="secondary-2-600" class="shrink-0" />
          {{ t('views.deployment-videowall.viewer.pinned.on-screen') }}
        </span>
        <span
          v-else-if="!streaming || failed"
          class="absolute inset-0 flex items-center justify-center px-2 text-center text-xs font-medium text-gray-warm-400"
        >
          {{ t('views.view-deployment.sections.viewer.empty.not-available') }}
        </span>
        <!-- Matches the frame background, so the fade-out shows no flash. -->
        <Transition leave-active-class="transition-opacity duration-300" leave-to-class="opacity-0">
          <div
            v-if="connecting"
            class="absolute inset-0 flex items-center justify-center bg-gray-warm-800"
          >
            <Spinner size="sm" />
          </div>
        </Transition>
      </div>
      <span class="min-w-0 px-0.5">
        <TruncatedText
          as="span"
          :title="props.desktop.user_name"
          class="block text-xs font-semibold text-gray-warm-900"
        />
        <span class="flex min-w-0 items-center gap-1 text-xs text-gray-warm-500">
          <Icon name="monitor" size="xs" stroke-color="gray-warm-500" class="shrink-0" />
          <TruncatedText as="span" :title="props.desktop.name" />
        </span>
      </span>
    </button>
    <Tooltip>
      <TooltipTrigger as-child>
        <button
          type="button"
          class="absolute right-3 top-3 flex size-7 cursor-pointer items-center justify-center rounded-md bg-gray-warm-900/80 opacity-0 outline-hidden group-hover:opacity-100 hover:bg-gray-warm-700 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-brand"
          :aria-label="t('views.deployment-videowall.viewer.pinned.unpin')"
          @click="emit('unpin')"
        >
          <Icon name="x" size="sm" stroke-color="gray-warm-100" />
        </button>
      </TooltipTrigger>
      <TooltipContent :title="t('views.deployment-videowall.viewer.pinned.unpin')" />
    </Tooltip>
  </div>
</template>
