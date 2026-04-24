<script setup lang="ts">
import type { TooltipContentEmits, TooltipContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TooltipContent, TooltipPortal, useForwardPropsEmits, TooltipArrow } from 'reka-ui'
import { cn } from '@/lib/utils'
import { Checkbox } from '@/components/ui/checkbox'

defineOptions({
  inheritAttrs: false
})

const props = withDefaults(
  defineProps<
    TooltipContentProps & { class?: HTMLAttributes['class'] } & {
      title: string
      subtitle?: string
      arrow?: boolean
      dismissLabel?: string
    }
  >(),
  {
    sideOffset: 4
  }
)

const emits = defineEmits<TooltipContentEmits & { dismiss: [] }>()

const delegatedProps = reactiveOmit(props, 'class', 'title', 'subtitle', 'arrow', 'dismissLabel')

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
      <p class="text-base-white font-semibold leading-[18px] text-[12px]">{{ props.title }}</p>
      <p class="text-gray-warm-300 mt-1 font-medium leading-[16px] text-[12px]">
        {{ props.subtitle }}
      </p>
      <div v-if="props.dismissLabel" class="mt-3 text-gray-warm-300">
        <Checkbox
          size="sm"
          :model-value="false"
          :title="props.dismissLabel"
          @update:model-value="emits('dismiss')"
        />
      </div>
      <TooltipArrow v-if="props.arrow" :width="16" :height="6" />
    </TooltipContent>
  </TooltipPortal>
</template>
