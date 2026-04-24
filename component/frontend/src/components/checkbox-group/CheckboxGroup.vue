<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { type Component, computed } from 'vue'
import { CheckboxGroupFeaturedIconItem, type FeaturedIconItem } from './featured-icon'
import { CheckboxGroupCardItem, type CardItem } from './card-item'
import { CheckboxGroupTextItem, type TextItem } from './text-item'
import { CheckboxGroupImageItem, type ImageItem } from './image-item'
import { cn } from '@/lib/utils'

interface Props extends PrimitiveProps {
  kind?: 'card' | 'text' | 'image' | 'featured-icon'
  type?: 'single' | 'multiple'
  checkType?: 'checkbox' | 'radio'
  loading?: boolean
  modelValue?: string | string[]
  disabled?: boolean
  items?: (CardItem | TextItem | ImageItem | FeaturedIconItem)[]
  direction?: string
}

const props = withDefaults(defineProps<Props>(), {
  kind: 'text',
  type: 'multiple',
  checkType: 'checkbox',
  direction: 'flex-col'
})

const emit = defineEmits(['update:modelValue'])

const componentMap: Record<string, Component> = {
  'featured-icon': CheckboxGroupFeaturedIconItem,
  card: CheckboxGroupCardItem,
  text: CheckboxGroupTextItem,
  image: CheckboxGroupImageItem
}

const currentComponent = computed(() => componentMap[props.kind])

const isItemSelected = (value: string) => {
  if (props.type === 'single') {
    return props.modelValue === value
  }
  return Array.isArray(props.modelValue) && props.modelValue.includes(value)
}

const selectItem = (value: string) => {
  if (props.type === 'single') {
    // Single selection: set the value directly
    emit('update:modelValue', value)
  } else {
    // Multiple selection: toggle value in array
    const currentValues = Array.isArray(props.modelValue) ? props.modelValue : []
    const index = currentValues.indexOf(value)

    if (index > -1) {
      // Remove if already selected
      const newValues = currentValues.filter((v) => v !== value)
      emit('update:modelValue', newValues)
    } else {
      // Add if not selected
      emit('update:modelValue', [...currentValues, value])
    }
  }
}
</script>

<template>
  <div :class="cn(`flex gap-3`, props.direction)">
    <component
      :is="currentComponent"
      v-for="item in props.items"
      :key="item.value"
      :item="item"
      :loading="props.loading"
      :is-selected="isItemSelected(item.value)"
      :check-type="props.checkType"
      :disabled="props.disabled"
      @check="selectItem(item.value)"
    />
  </div>
</template>
