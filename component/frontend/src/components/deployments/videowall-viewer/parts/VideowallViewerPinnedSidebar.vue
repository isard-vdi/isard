<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { VideowallDesktop } from '@/lib/videowall'

import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import VideowallViewerPinnedPreview from './VideowallViewerPinnedPreview.vue'
import { BAR_BUTTON } from '../constants'

interface Props {
  pinned: VideowallDesktop[]
  onScreenId: string | null
}

const props = defineProps<Props>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ select: [id: string]; unpin: [id: string] }>()

const { t } = useI18n()
</script>

<template>
  <aside
    class="flex shrink-0 flex-col border-l border-gray-warm-200 bg-base-white"
    :class="open ? 'w-64' : 'w-12'"
  >
    <div
      class="flex h-11 shrink-0 items-center gap-2 px-1.5"
      :class="open ? 'justify-between pl-3' : 'flex-col justify-center'"
    >
      <span
        v-if="open"
        class="truncate text-xs font-semibold uppercase tracking-wide text-gray-warm-500"
      >
        {{ t('views.deployment-videowall.viewer.pinned.title', { count: props.pinned.length }) }}
      </span>
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            type="button"
            :class="BAR_BUTTON"
            :aria-label="
              open
                ? t('views.deployment-videowall.viewer.pinned.collapse')
                : t('views.deployment-videowall.viewer.pinned.expand')
            "
            :aria-expanded="open"
            @click="open = !open"
          >
            <Icon
              :name="open ? 'chevron-right-double' : 'chevron-left-double'"
              size="md"
              stroke-color="gray-warm-600"
            />
          </button>
        </TooltipTrigger>
        <TooltipContent
          :title="
            open
              ? t('views.deployment-videowall.viewer.pinned.collapse')
              : t('views.deployment-videowall.viewer.pinned.expand')
          "
        />
      </Tooltip>
    </div>
    <!-- Hidden, not unmounted, when collapsed: pinned ones keep streaming. -->
    <div v-show="open" class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-1.5">
      <VideowallViewerPinnedPreview
        v-for="entry in props.pinned"
        :key="entry.id"
        :desktop="entry"
        :on-screen="entry.id === props.onScreenId"
        @select="emit('select', entry.id)"
        @unpin="emit('unpin', entry.id)"
      />
    </div>
    <div v-if="!open" class="flex flex-col items-center gap-1 pt-1 text-gray-warm-500">
      <Icon name="pin-02" size="sm" stroke-color="gray-warm-500" />
      <span class="text-xs font-medium">{{ props.pinned.length }}</span>
    </div>
  </aside>
</template>
