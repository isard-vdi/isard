<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed } from 'vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'

export interface FeaturedIconItem {
  color?:
    | 'brand'
    | 'gray'
    | 'success'
    | 'warning'
    | 'error'
    | 'current'
    | 'persistent'
    | 'temporary'
  icon?: string
  title?: string
  description?: string
  value: string
  disabled?: boolean
}

interface Props extends PrimitiveProps {
  loading?: boolean
  checkType?: 'checkbox' | 'radio'
  isSelected?: boolean
  disabled?: boolean
  item: FeaturedIconItem
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
    kind: 'featured-icon',
    selected: props.isSelected,
    disabled: isDisabled.value,
    loading: props.loading
  })
)

const selectItem = () => {
  if (!isDisabled.value) {
    emit('check')
  }
}
</script>

<template>
  <div :class="containerClasses" @click="selectItem">
    <div v-if="loading" class="flex items-center gap-3 mx-2 mb-3">
      <Skeleton class="mt-2 h-8 aspect-square rounded-full" />
      <Skeleton class="h-4 w-full" />
    </div>
    <template v-else>
      <div class="flex items-center gap-3">
        <FeaturedIconOutline :name="item.icon" kind="filled" :color="item.color" />
        <div class="flex-1">
          <p :class="cn('text-sm', isSelected ? 'font-bold' : 'font-regular')">
            {{ item.title }}
          </p>
          <p class="text-sm font-regular text-gray-warm-700">{{ item.description }}</p>
        </div>
        <Icon v-if="isDisabled" name="lock-01" size="lg" stroke-color="secondary-1-600" />
        <Checkbox v-else :model-value="isSelected" :type="checkType" />
      </div>
    </template>
  </div>
</template>
