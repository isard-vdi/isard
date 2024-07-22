<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import {
  TooltipArrow,
  TooltipContent,
  type TooltipContentEmits,
  type TooltipContentProps,
  TooltipPortal,
  useForwardPropsEmits
} from 'radix-vue'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false
})

const props = withDefaults(
  defineProps<
    TooltipContentProps & { class?: HTMLAttributes['class'] } & {
      title: string
      subtitle?: string
      arrow?: boolean
    }
  >(),
  {
    sideOffset: 4
  }
)

const emits = defineEmits<TooltipContentEmits>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props

  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <TooltipPortal>
    <!-- TODO: The margin with the trigger element should be 4px, currently it's not working -->
    <TooltipContent
      v-bind="{ ...forwarded, ...$attrs }"
      :side-offset="4"
      :class="
        cn(
          `
      rounded-md bg-gray-warm-900 max-w-[320px] p-[12px]
      z-50 overflow-hidden
      shadow-md animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out 
      data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 
      data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 
      data-[side=top]:slide-in-from-bottom-2`,
          props.class
        )
      "
    >
      <p class="text-base-white font-[600] leading-[18px] text-[12px]">{{ props.title }}</p>
      <p class="text-gray-warm-300 mt-1 font-[500] leading-[16px] text-[12px]">
        {{ props.subtitle }}
      </p>
      <TooltipArrow v-if="props.arrow" :width="16" :height="6" />
    </TooltipContent>
  </TooltipPortal>
</template>
