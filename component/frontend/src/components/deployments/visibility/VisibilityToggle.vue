<script setup lang="ts">
import { computed } from 'vue'
import { CheckboxIndicator, CheckboxRoot } from 'reka-ui'
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'

export type VisibilityState = boolean | 'indeterminate'

const props = withDefaults(
  defineProps<{
    modelValue: VisibilityState
    disabled?: boolean
    /** Render as a plain indicator: same visual language, no interaction. */
    readonly?: boolean
    /** Accessible name — the control carries no visible text. */
    label: string
    size?: 'sm' | 'md'
  }>(),
  { disabled: false, readonly: false, size: 'sm' }
)

const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

// Built on the reka-ui primitives rather than `ui/checkbox` because that
// wrapper turns a click into a three-state cycle when `indeterminate` is
// set, letting a user *set* "mixed". `CheckboxRoot` maps indeterminate to
// true on click, which is what an aggregate control should do.
//
// `minus` for mixed: there is no eye glyph for a partial state, and the
// dash is the universal indeterminate mark.
const iconName = computed(() => {
  if (props.modelValue === 'indeterminate') return 'minus'
  return props.modelValue ? 'eye' : 'eye-off'
})

/** The `data-state` reka-ui would set, so the readonly span can share the
 *  same class list instead of duplicating the palette. */
const dataState = computed(() => {
  if (props.modelValue === 'indeterminate') return 'indeterminate'
  return props.modelValue ? 'checked' : 'unchecked'
})

const rootClass = computed(() =>
  cn(
    'inline-flex items-center justify-center rounded-md border outline-none transition-colors',
    props.size === 'md' ? 'size-7' : 'size-6',
    'data-[state=checked]:bg-brand-700 data-[state=checked]:border-brand-700',
    'data-[state=indeterminate]:bg-warning-100 data-[state=indeterminate]:border-warning-400',
    'data-[state=unchecked]:bg-base-white data-[state=unchecked]:border-gray-warm-300',
    // Without a pointer and a lift on hover the boxed icon reads as a badge,
    // and nobody tries clicking it.
    !props.readonly && [
      'cursor-pointer',
      'hover:ring-[3px] hover:ring-brand-200 hover:shadow-sm',
      'focus-visible:ring-[3px] focus-visible:ring-brand-200',
      'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:ring-0 disabled:hover:shadow-none'
    ]
  )
)

const iconColor = computed(() => (props.modelValue === true ? 'base-white' : 'gray-warm-600'))
</script>

<template>
  <span
    v-if="props.readonly"
    role="img"
    :data-state="dataState"
    :aria-label="props.label"
    :class="rootClass"
  >
    <span class="grid place-content-center">
      <Icon :name="iconName" size="xs" :stroke-color="iconColor" />
    </span>
  </span>

  <CheckboxRoot
    v-else
    :model-value="props.modelValue"
    :disabled="props.disabled"
    :aria-label="props.label"
    :class="rootClass"
    @update:model-value="(value) => emit('update:modelValue', value === true)"
  >
    <!-- force-mount so the eye-off glyph still renders while unchecked;
         reka-ui hides the indicator in that state by default. -->
    <CheckboxIndicator force-mount class="grid place-content-center">
      <Icon :name="iconName" size="xs" :stroke-color="iconColor" />
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
