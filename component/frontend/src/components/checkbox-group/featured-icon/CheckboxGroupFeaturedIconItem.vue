<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed, ref, watch } from 'vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
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
  // Extra line for the info tooltip, under the description.
  note?: string
  tooltip?: { title: string; description?: string }
}

interface Props extends PrimitiveProps {
  loading?: boolean
  checkType?: 'checkbox' | 'radio'
  isSelected?: boolean
  disabled?: boolean
  item: FeaturedIconItem
  hideDescription?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  as: 'div',
  checkType: 'checkbox',
  isSelected: false,
  loading: false,
  disabled: false,
  hideDescription: false
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

const infoOpen = ref(false)
const disabledReasonOpen = ref(false)

// Both tooltips would stack on top of each other: the info one wins.
watch(infoOpen, (open) => {
  if (open) {
    disabledReasonOpen.value = false
  }
})

const selectItem = () => {
  if (!isDisabled.value) {
    emit('check')
  }
}
</script>

<template>
  <!-- Disabled without a reason reads as a bug: the tooltip carries the why. -->
  <Tooltip v-model:open="disabledReasonOpen" :disabled="!item.tooltip">
    <TooltipTrigger as-child>
      <div :class="cn(containerClasses, 'relative')" @click="selectItem">
        <div v-if="loading" class="w-26 flex items-center gap-3 mx-2 mb-3">
          <Skeleton class="mt-2 h-8 aspect-square rounded-full" />
          <Skeleton class="h-4 w-full" />
        </div>
        <div v-else class="flex items-center gap-3">
          <FeaturedIconOutline :name="item.icon" kind="filled" :color="item.color" size="sm" />
          <div class="flex-1">
            <p :class="cn('text-sm', isSelected ? 'font-bold' : 'font-regular')">
              {{ item.title }}
            </p>
            <p v-if="!hideDescription" class="text-sm font-regular text-gray-warm-700">
              {{ item.description }}
            </p>
          </div>
          <Icon v-if="isDisabled" name="lock-01" size="lg" stroke-color="secondary-1-600" />
          <Checkbox v-else :model-value="isSelected" :type="checkType" />
        </div>
        <Tooltip v-if="hideDescription && item.description" v-model:open="infoOpen">
          <TooltipTrigger as-child>
            <div
              class="absolute -top-2 -right-2 flex h-6 w-6 cursor-help items-center justify-center rounded-full border border-gray-warm-300 bg-base-white"
              @click.stop
              @pointermove.stop
            >
              <Icon name="info-circle" size="xs" stroke-color="gray-warm-500" />
            </div>
          </TooltipTrigger>
          <TooltipContent :title="item.description" :subtitle="item.note" />
        </Tooltip>
      </div>
    </TooltipTrigger>
    <TooltipContent
      v-if="item.tooltip"
      :title="item.tooltip.title"
      :subtitle="item.tooltip.description"
    />
  </Tooltip>
</template>
