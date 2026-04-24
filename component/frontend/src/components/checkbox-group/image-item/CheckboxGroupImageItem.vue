<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed } from 'vue'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'

export interface ImageItem {
  image?: string
  label?: string
  value: string
  disabled?: boolean
}

interface Props extends PrimitiveProps {
  loading?: boolean
  isSelected?: boolean
  disabled?: boolean
  item: ImageItem
}

const props = withDefaults(defineProps<Props>(), {
  as: 'div',
  checkType: 'checkbox',
  isSelected: false,
  loading: false,
  disabled: false
})

const emit = defineEmits(['check'])

const isDisabled = computed(() => props.disabled || props.item.disabled)
const containerClasses = computed(() =>
  checkboxGroupItemVariants({
    kind: 'image',
    selected: props.isSelected,
    disabled: isDisabled.value,
    loading: props.loading
  })
)

const selectItem = () => {
  if (!isDisabled.value && !props.loading) {
    emit('check')
  }
}
</script>

<template>
  <div
    :class="
      cn(
        containerClasses,
        'w-34 h-[111px] p-3 border border-gray-warm-300 rounded-lg relative',

        // Focus state with focus within
        'focus-within:outline-hidden focus-within:ring-sm focus-within:ring-offset-0 focus-within:ring-4',
        'focus-within:ring-gray-warm-100',

        // Selected and loading state
        isSelected &&
          'border-2 border-brand-700 focus-within:border-brand-700 focus-within:ring-brand',
        loading && 'cursor-wait'
      )
    "
    @click="selectItem"
  >
    <div v-if="loading" class="flex flex-col gap-3">
      <Skeleton class="h-7 w-full rounded-lg" />
      <Skeleton class="h-4 w-2/3 mx-auto" />
    </div>
    <template v-else>
      <div class="absolute top-2 right-2">
        <Checkbox
          v-if="!isDisabled"
          :model-value="isSelected"
          type="checkbox"
          size="sm"
          class="bg-base-white rounded"
        />
      </div>
      <div class="flex flex-col items-center gap-3">
        <img
          v-if="item.image"
          :src="item.image"
          :alt="item.label"
          class="w-auto h-auto object-contain"
        />
        <p v-if="item.label" class="text-xs font-medium leading-4 text-gray-warm-700 text-center">
          {{ item.label }}
        </p>
      </div>
    </template>
  </div>
</template>
