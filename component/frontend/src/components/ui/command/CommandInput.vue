<script setup lang="ts">
import type { ListboxFilterProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { Search } from 'lucide-vue-next'
import { ListboxFilter, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'
import { useCommand } from '.'

defineOptions({
  inheritAttrs: false
})

const props = defineProps<
  ListboxFilterProps & {
    class?: HTMLAttributes['class']
  }
>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)

const { filterState } = useCommand()
</script>

<template>
  <div
    class="flex items-center px-[14px] py-[10px] border-b border-gray-200 focus:border-gray-warm-200"
    cmdk-input-wrapper
  >
    <Search class="mr-[8px] h-[20px] w-[20px] shrink-0 opacity-50" />
    <ListboxFilter
      v-bind="{ ...forwardedProps, ...$attrs }"
      v-model="filterState.search"
      auto-focus
      :class="
        cn(
          `flex w-full
rounded-md bg-transparent outline-hidden
        text-md text-gray-warm-900 font-medium
placeholder:text-gray-warm-500
disabled:cursor-not-allowed disabled:opacity-50`,
          props.class
        )
      "
    />
  </div>
</template>
