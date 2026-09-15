<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed, type HTMLAttributes } from 'vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'
import { checkboxGroupCardVariants } from './index'

export interface CardItem {
  icon?: string
  color?:
    | 'brand'
    | 'gray'
    | 'success'
    | 'warning'
    | 'error'
    | 'current'
    | 'persistent'
    | 'temporary'
  title?: string
  image?: string
  description?: string
  warning?: string
  value: string
  disabled?: boolean
  class?: HTMLAttributes['class']
}

interface Props extends PrimitiveProps {
  loading?: boolean
  checkType?: 'checkbox' | 'radio'
  isSelected?: boolean
  disabled?: boolean
  item: CardItem
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
  cn(
    checkboxGroupItemVariants({
      kind: 'card',
      selected: props.isSelected,
      disabled: isDisabled.value,
      loading: props.loading
    }),
    checkboxGroupCardVariants({
      selected: props.isSelected,
      disabled: isDisabled.value
    }),
    props.item.class
  )
)

const handleClick = () => {
  if (isDisabled.value) return
  emit('check')
}
</script>

<template>
  <div :class="containerClasses" @click="handleClick">
    <div v-if="loading" class="flex flex-col gap-3 p-6 w-full">
      <Skeleton class="h-8 w-full rounded-lg" />
      <Skeleton class="h-48 w-full rounded-lg" />
      <Skeleton class="h-12 w-full" />
    </div>
    <template v-else>
      <header
        v-if="item.icon || item.title"
        class="flex w-full items-center p-3 pr-5.5 justify-between"
      >
        <div class="flex gap-3 items-center">
          <FeaturedIconOutline
            v-if="item.icon"
            :name="item.icon"
            :color="item.color ?? 'brand'"
            kind="filled"
            size="md"
          />
          <h3 v-if="item.title" class="text-lg font-semibold leading-7 text-gray-warm-700 flex-1">
            {{ item.title }}
          </h3>
        </div>
        <!-- Disabled without a mark reads as a bug: the lock says why it cannot be picked. -->
        <Icon
          v-if="isDisabled"
          name="lock-01"
          size="lg"
          stroke-color="secondary-1-600"
          class="ml-auto"
        />
        <Checkbox v-else :model-value="isSelected" :type="checkType" class="ml-auto" />
      </header>

      <div
        v-if="item.image || item.description || item.warning"
        class="flex flex-col items-center p-4 pt-0 gap-3 w-full"
      >
        <img
          v-if="item.image"
          :src="item.image"
          :alt="item.title"
          class="w-auto h-auto max-h-[202px] object-contain"
        />
        <p
          v-if="item.description"
          class="text-base font-normal leading-6 text-gray-warm-600 text-center"
        >
          {{ item.description }}
        </p>
        <p
          v-if="item.warning"
          class="text-base font-semibold leading-6 text-gray-warm-700 text-center"
        >
          {{ item.warning }}
        </p>
      </div>
    </template>
  </div>
</template>
