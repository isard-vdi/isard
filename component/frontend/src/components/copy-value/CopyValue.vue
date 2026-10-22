<script setup lang="ts">
import { computed, ref, type HTMLAttributes } from 'vue'
import { useI18n } from 'vue-i18n'
import { useClipboard } from '@vueuse/core'

import { useIsTextTruncated } from '@/composables/useIsTextTruncated'
import { cn } from '@/lib/utils'

import { Icon } from '@/components/icon'
import { type Props as IconProps } from '@/components/icon/Icon.vue'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const { t } = useI18n()

// The value and the copy icon form a single button, so the whole text is a
// click target instead of only the (tiny) icon.
interface Props {
  value: string
  iconSize?: IconProps['size']
  strokeColor?: string
  class?: HTMLAttributes['class']
  textClass?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  iconSize: 'xs',
  strokeColor: 'currentColor',
  class: undefined,
  textClass: undefined
})

const { copy, copied } = useClipboard({ legacy: true, copiedDuring: 1000 })

const textRef = ref<HTMLElement | null>(null)
const { isTruncated } = useIsTextTruncated(textRef, () => props.value)

const label = computed(() => `${t('common.actions.copy')} ${props.value}`)
</script>

<template>
  <!-- disable-closing-trigger: keep the tooltip open on click so the "copied" text is visible -->
  <Tooltip disable-closing-trigger>
    <TooltipTrigger as-child>
      <button
        type="button"
        :aria-label="label"
        :class="
          cn(
            'inline-flex min-h-6 min-w-0 cursor-pointer items-center gap-1.5 rounded-sm -mx-1 -my-1 px-1 text-start',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            props.class
          )
        "
        @click.stop="copy(props.value)"
      >
        <span ref="textRef" :class="cn('min-w-0 truncate', props.textClass)">{{
          props.value
        }}</span>
        <Icon
          :name="copied ? 'check' : 'copy-06'"
          :size="props.iconSize"
          :stroke-color="props.strokeColor"
          class="shrink-0"
          aria-hidden="true"
        />
      </button>
    </TooltipTrigger>
    <TooltipContent
      :title="copied ? t('common.actions.copied') : t('common.actions.copy')"
      :subtitle="isTruncated ? props.value : undefined"
    />
  </Tooltip>
  <span class="sr-only" aria-live="polite">{{ copied ? t('common.actions.copied') : '' }}</span>
</template>
