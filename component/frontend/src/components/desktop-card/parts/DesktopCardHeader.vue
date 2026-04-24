<script setup lang="ts">
import { computed, inject, ref } from 'vue'

import { Icon } from '@/components/icon'
import { Progress } from '@/components/ui/progress'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

import {
  CARD_SIZE_INJECTION_KEY,
  cardHeaderNameVariants,
  cardHeaderDescriptionVariants,
  cardHeaderNotificationVariants
} from '..'

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const nameRef = ref<HTMLElement | null>(null)
const descriptionRef = ref<HTMLElement | null>(null)

interface Props {
  notificationText?: string | null
  name: string
  description: string
  downloadProgress?: {
    size: string
    percentage: number
  }
}

const props = withDefaults(defineProps<Props>(), {
  notificationText: null,
  downloadProgress: undefined
})

const emit = defineEmits<{
  close: []
}>()

const showDownloadProgress = computed(() => {
  return props.downloadProgress && (size === 'md' || size === 'lg' || size === 'xl')
})

const { isTruncated: isNameTruncated } = useIsTextTruncated(nameRef, () => props.name)
const { isTruncated: isDescriptionTruncated } = useIsTextTruncated(
  descriptionRef,
  () => props.description
)
</script>

<template>
  <div v-if="props.notificationText" :class="cardHeaderNotificationVariants({ size })">
    <Icon name="info-circle" stroke-color="warning-600" class="h-3.5 w-3.5 shrink-0" />
    <span class="truncate">{{ props.notificationText }}</span>
  </div>

  <Tooltip>
    <TooltipTrigger as-child>
      <div ref="nameRef" :class="cardHeaderNameVariants({ size })">
        <span>{{ props.name }}</span>
      </div>
    </TooltipTrigger>
    <TooltipContent v-if="isNameTruncated" :title="props.name" />
  </Tooltip>

  <Tooltip v-if="size !== '2xs'">
    <TooltipTrigger as-child>
      <p ref="descriptionRef" :class="cardHeaderDescriptionVariants({ size })">
        {{ props.description }}
      </p>
    </TooltipTrigger>
    <TooltipContent v-if="isDescriptionTruncated" :title="props.description" />
  </Tooltip>

  <div v-if="showDownloadProgress" class="mt-2 px-3 text-start">
    <div class="flex justify-between text-xs text-white/80 mb-1">
      <span>{{ props.downloadProgress!.size }}</span>
      <span>{{ props.downloadProgress!.percentage }}%</span>
    </div>
    <Progress
      :model-value="props.downloadProgress!.percentage"
      class="w-full bg-base-white/20 text-base-white"
    ></Progress>
  </div>
</template>
