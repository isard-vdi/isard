<script lang="ts" setup>
import type { CalendarPrevProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { CalendarPrev, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'
import { Icon } from '@/components/icon'

const props = defineProps<CalendarPrevProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <CalendarPrev
    data-slot="calendar-prev-button"
    :class="cn('rounded-lg hover:bg-gray-warm-50 transition-colors', props.class)"
    v-bind="forwardedProps"
  >
    <slot>
      <Icon name="chevron-left" size="sm" class="text-gray-warm-500" />
    </slot>
  </CalendarPrev>
</template>
