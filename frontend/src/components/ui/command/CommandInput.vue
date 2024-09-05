<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { Search } from 'lucide-vue-next'
import { ComboboxInput, type ComboboxInputProps, useForwardProps } from 'radix-vue'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<
  ComboboxInputProps & {
    class?: HTMLAttributes['class']
  }
>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props

  return delegated
})

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <div
    class="flex items-center px-[14px] py-[10px] border-b focus:border-gray-warm-200"
    cmdk-input-wrapper
  >
    <Search class="mr-[8px] h-[20px] w-[20px] shrink-0 opacity-50" />
    <ComboboxInput
      v-bind="{ ...forwardedProps, ...$attrs }"
      auto-focus
      :class="
        cn(
          `flex w-full
        rounded-md bg-transparent outline-none
        text-md text-gray-warm-900 font-medium
        placeholder:text-gray-warm-500
        disabled:cursor-not-allowed disabled:opacity-50`,
          props.class
        )
      "
    />
  </div>
</template>
