<script setup lang="ts">
import { type PrimitiveProps } from 'reka-ui'
import { computed, type HTMLAttributes } from 'vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'
import { checkboxGroupCardVariants } from './index'

export interface CardItem {
  icon?: string
  title?: string
  image?: string
  description?: string
  value: string
  disabled?: boolean
  class?: HTMLAttributes['class']
}

interface Props extends PrimitiveProps {
  loading?: boolean
  isSelected?: boolean
  disabled?: boolean
  item: CardItem
}

const props = withDefaults(defineProps<Props>(), {
  as: 'div',
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
      <header v-if="item.icon || item.title" class="flex items-center gap-3 p-3">
        <FeaturedIconOutline
          v-if="item.icon"
          :name="item.icon"
          color="brand"
          kind="filled"
          size="md"
        />
        <h3 v-if="item.title" class="text-lg font-semibold leading-7 text-gray-warm-700 flex-1">
          {{ item.title }}
        </h3>
      </header>

      <div v-if="item.image || item.description" class="flex flex-col items-center p-4 gap-3">
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
      </div>
    </template>
  </div>
</template>
