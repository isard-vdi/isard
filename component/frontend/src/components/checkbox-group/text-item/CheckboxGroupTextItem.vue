<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed } from 'vue'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'

export interface TextItem {
  icon?: string
  label?: string
  value: string
  disabled?: boolean
}

interface Props extends PrimitiveProps {
  loading?: boolean
  checkType?: 'checkbox' | 'radio'
  isSelected?: boolean
  disabled?: boolean
  item: TextItem
}

const props = withDefaults(defineProps<Props>(), {
  as: 'div',
  checkType: 'radio',
  isSelected: false,
  loading: false,
  disabled: false
})

const emit = defineEmits(['check'])

const isDisabled = computed(() => props.disabled || props.item.disabled)

const containerClasses = computed(() =>
  checkboxGroupItemVariants({
    kind: 'text',
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
        'max-w-36 max-h-12 p-3-5 bg-white flex-row border-gray-warm-300 justify-start items-center rounded-lg gap-3 cursor-pointer',

        // Selected, disabled and loading state
        isSelected && 'border-gray-warm-600 border-2',
        disabled && 'bg-gray-warm-100',
        loading && 'cursor-wait'
      )
    "
    @click="selectItem"
  >
    <div v-if="loading" class="flex items-center gap-3 w-full">
      <Skeleton class="h-4 flex-1" />
    </div>
    <template v-else>
      <Icon
        v-if="item.icon"
        :name="item.icon"
        size="md"
        class="shrink-0"
        :stroke-color="isSelected ? 'gray-warm-800' : 'gray-warm-500'"
      />
      <div
        :class="
          cn(
            'justify-start text-sm leading-5',
            isSelected ? 'text-gray-warm-700 font-bold' : 'text-gray-warm-500 font-medium'
          )
        "
      >
        {{ item.label }}
      </div>
    </template>
  </div>
</template>
