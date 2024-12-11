<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import type { CheckboxRootEmits, CheckboxRootProps } from 'radix-vue'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'radix-vue'
import { Check } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<CheckboxRootEmits>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props

  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    v-bind="forwarded"
    :class="
      cn(
        `peer h-[20px] w-[20px] shrink-0 rounded-[6px] border border-gray-warm-300 bg-base-white
        focus-visible:ring-4 focus-visible:ring-offset-0 focus-visible:ring-[rgba(179,_170,_152,_0.14)] data-[state=checked]:focus-visible:ring-[rgba(32,_91,_128,_0.50)] 
        disabled:cursor-not-allowed disabled:opacity-50 
        data-[state=checked]:bg-brand-700 data-[state=checked]:text-base-white data-[state=checked]:border-brand-700`,
        props.class
      )
    "
  >
    <CheckboxIndicator class="flex h-full w-full items-center justify-center text-current">
      <slot>
        <Check class="h-4 w-4" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
