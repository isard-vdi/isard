<script setup lang="ts">
import type { SwitchRootEmits, SwitchRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { SwitchRoot, SwitchThumb, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<SwitchRootProps & { size?: 'sm' | 'md'; class?: HTMLAttributes['class'] }>(),
  { size: 'sm', class: '' }
)

const emits = defineEmits<SwitchRootEmits>()

const delegatedProps = reactiveOmit(props, 'class', 'size')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SwitchRoot
    data-slot="switch"
    v-bind="forwarded"
    :class="
      cn(
        props.size === 'md' ? 'h-6 w-11' : 'h-5 w-9',
        'peer inline-flex shrink-0 cursor-pointer items-center rounded-xl p-0.5 overflow-hidden transition-colors outline-none',
        'data-[state=unchecked]:bg-gray-warm-200 data-[state=checked]:bg-brand-700',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'disabled:data-[state=checked]:bg-gray-warm-100 disabled:data-[state=unchecked]:bg-gray-warm-100',
        'focus-visible:ring-sm focus-visible:ring-offset-0 focus-visible:ring-2 ',
        'data-[state=checked]:focus-visible:ring-brand data-[state=unchecked]:focus-visible:ring-gray-secondary focus-visible:data-[state=unchecked]:bg-gray-warm-100',
        'hover:data-[state=checked]:bg-brand-800 active:data-[state=checked]:bg-brand-800',
        'hover:data-[state=unchecked]:bg-gray-warm-300',
        props.class
      )
    "
  >
    <SwitchThumb
      :class="
        cn(
          props.size === 'md' ? 'h-5 w-5' : 'h-4 w-4',
          'pointer-events-none block rounded-full shadow-lg ring-0 transition-transform data-[state=unchecked]:translate-x-0',
          props.size === 'md'
            ? 'data-[state=checked]:translate-x-5'
            : 'data-[state=checked]:translate-x-4',

          'bg-white disabled:bg-gray-warm-50',
          'relative z-10'
        )
      "
    >
    </SwitchThumb>
  </SwitchRoot>
</template>
