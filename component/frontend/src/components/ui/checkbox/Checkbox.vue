<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { Icon } from '@/components/icon'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'
import { type CheckboxVariants, checkboxVariants } from '.'

const props = defineProps<
  CheckboxRootProps & {
    indeterminate?: CheckboxVariants['indeterminate'] // set to support 'intermediate' state
    title?: string
    subtitle?: string
    type?: CheckboxVariants['type']
    size?: CheckboxVariants['size']
    textPosition?: CheckboxVariants['textPosition']
    class?: HTMLAttributes['class']
  }
>()
const emits = defineEmits<CheckboxRootEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)

// Computed properties for reusable values
const hasTextContent = computed(() => !!(props.title || props.subtitle))

const iconStrokeColor = computed(() => (props.disabled ? 'gray-warm-300' : 'base-white'))

const iconSize = computed(() => (props.size === 'sm' ? 'xs' : 'sm'))

const iconName = computed(() => {
  if (props.type === 'radio') {
    return props.indeterminate ? 'minus' : 'dot'
  } else {
    if (props.modelValue === true) {
      return 'check'
    } else if (props.indeterminate && props.modelValue === 'indeterminate') {
      return 'minus'
    } else {
      return ''
    }
  }
})

const textOrderClass = computed(() => (props.textPosition === 'before' ? 'order-1' : 'order-2'))

const checkboxOrderClass = computed(() => (props.textPosition === 'before' ? 'order-2' : 'order-1'))

const checkboxClasses = computed(() =>
  cn(
    checkboxVariants({
      type: props.type,
      size: props.size,
      indeterminate: props.indeterminate || false
    }),
    checkboxOrderClass.value,
    hasTextContent.value && 'mt-0.5',
    props.class
  )
)

// Handle three-state cycle when indeterminate is enabled
const handleClick = (event: MouseEvent) => {
  if (props.indeterminate) {
    event.preventDefault()
    event.stopPropagation()

    // Implement three-state cycle: false -> true -> 'indeterminate' -> false
    if (props.modelValue === false) {
      emits('update:modelValue', true)
    } else if (props.modelValue === true) {
      emits('update:modelValue', 'indeterminate')
    } else {
      emits('update:modelValue', false)
    }
  }
}
</script>

<template>
  <label
    class="flex cursor-pointer group [[data-state=indeterminate]]/indicator:group"
    :class="cn(hasTextContent ? 'items-start' : 'items-center')"
  >
    <CheckboxRoot
      data-slot="checkbox"
      v-bind="forwarded"
      :class="checkboxClasses"
      @click.capture="handleClick"
    >
      <CheckboxIndicator
        data-slot="checkbox-indicator"
        :class="cn('grid place-content-center text-current transition-none')"
      >
        <slot>
          <Icon
            :name="iconName"
            :size="iconSize"
            :class="cn('group-[[data-state=indeterminate]]/indicator:hidden')"
            :stroke-color="iconStrokeColor"
          />
        </slot>
      </CheckboxIndicator>
    </CheckboxRoot>
    <div v-if="title || subtitle" :class="cn(textOrderClass, 'items-start flex flex-col mx-3')">
      <p v-if="title" class="text-sm font-medium">{{ title }}</p>
      <p v-if="subtitle" class="text-xs font-regular">{{ subtitle }}</p>
    </div>
  </label>
</template>
