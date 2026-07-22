<script lang="ts" setup>
import type { CalendarNextProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { CalendarNext, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'
import { Icon } from '@/components/icon'

const props = defineProps<CalendarNextProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <CalendarNext
    data-slot="calendar-next-button"
    :class="cn('rounded-lg hover:bg-gray-warm-50 transition-colors', props.class)"
    v-bind="forwardedProps"
  >
    <slot>
      <Icon name="chevron-right" size="sm" class="text-gray-warm-500" />
    </slot>
  </CalendarNext>
</template>
