<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useIntersectionObserver } from '@vueuse/core'

import { canViewInBrowser, type VideowallDesktop } from '@/lib/videowall'
import { cn } from '@/lib/utils'
import { useVideowallStream } from '@/composables/useVideowallStream'

import { Icon } from '@/components/icon'
import { TruncatedText } from '@/components/truncated-text'
import NoVNC from '@/components/noVNC/NoVNC.vue'
import { Spinner } from '@/components/ui/spinner'

interface Props {
  desktop: VideowallDesktop
}

const props = defineProps<Props>()

const emit = defineEmits<{ select: [] }>()

const { t } = useI18n()

const root = ref<HTMLElement | null>(null)
// Only tiles scrolled into view stream.
const inView = ref(false)
useIntersectionObserver(root, ([entry]) => (inView.value = entry?.isIntersecting ?? false))

const viewable = computed(() => canViewInBrowser(props.desktop))
const { vncValues, connectionKey, connecting, failed, onConnect, onDisconnect } =
  useVideowallStream(() => props.desktop, inView)
</script>

<template>
  <button
    ref="root"
    type="button"
    :class="
      cn(
        'group relative aspect-video w-full overflow-hidden rounded-md bg-gray-warm-800 text-left outline-hidden ring-1 ring-gray-warm-700',
        viewable
          ? 'cursor-pointer transition-shadow hover:ring-4 hover:ring-brand-400 focus-visible:ring-4 focus-visible:ring-brand-400'
          : 'cursor-default'
      )
    "
    :disabled="!viewable"
    :aria-label="`${props.desktop.user_name} · ${props.desktop.name}`"
    @click="emit('select')"
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
      class="absolute inset-0"
      @first-frame="onConnect"
      @disconnect="onDisconnect"
    />
    <span
      v-if="!viewable || failed"
      class="absolute inset-0 flex items-center justify-center px-2 text-center text-xs font-medium text-gray-warm-400"
    >
      {{ t('views.view-deployment.sections.viewer.empty.not-available') }}
    </span>
    <Transition leave-active-class="transition-opacity duration-300" leave-to-class="opacity-0">
      <span
        v-if="connecting"
        class="absolute inset-0 flex items-center justify-center bg-gray-warm-800"
      >
        <Spinner size="sm" />
      </span>
    </Transition>
    <span
      class="absolute inset-x-0 bottom-0 flex min-w-0 items-center gap-1.5 bg-gray-warm-900/80 px-2 py-1 text-xs"
    >
      <TruncatedText
        as="span"
        :title="props.desktop.user_name"
        class="font-semibold text-base-white"
      />
      <Icon name="monitor" size="xs" stroke-color="gray-warm-500" class="shrink-0" />
      <TruncatedText as="span" :title="props.desktop.name" class="text-gray-warm-300" />
    </span>
  </button>
</template>
