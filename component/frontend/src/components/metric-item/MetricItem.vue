<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Badge } from '@/components/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { computed, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import type { ComponentProps } from 'vue-component-type-helpers'
import { Icon } from '@/components/icon'

const { t } = useI18n()

type BadgeProps = ComponentProps<typeof Badge>
type Status = 'low' | 'medium' | 'full'

const props = withDefaults(
  defineProps<{
    title: string
    total?: number
    current: number
  }>(),
  {
    total: Infinity
  }
)

const progress = computed(() =>
  Math.min(
    100,
    props.current === 0
      ? props.total === 0
        ? 100
        : 0
      : (props.current / (props.total || props.current)) * 100
  )
)
const status = computed<'low' | 'medium' | 'full'>(() => {
  if (progress.value < 50) return 'low'
  if (progress.value < 100) return 'medium'
  return 'full'
})

const badges = {
  low: {
    color: 'lightgreen',
    content: t('components.metric-item.labels.low')
  },
  medium: {
    color: 'lightyellow',
    content: t('components.metric-item.labels.medium')
  },
  full: {
    color: 'lightred',
    content: t('components.metric-item.labels.high')
  }
} satisfies Record<
  Status,
  {
    color: BadgeProps['color']
    content: BadgeProps['content']
  }
>

const progressClass = {
  low: 'text-success-400',
  medium: 'text-warning-400',
  full: 'text-error-400'
} satisfies Record<Status, string>

function usePrettyNumber(source: MaybeRefOrGetter<number>): Readonly<Ref<string>> {
  return computed(() => {
    const value = toValue(source)
    if (value === Infinity) return '∞'
    return value.toString().replace(/(\.\d{2})\d+$/, '$1')
  })
}

const prettyCurrent = usePrettyNumber(props.current)
const prettyTotal = usePrettyNumber(props.total)
</script>

<template>
  <div class="max-w-sm rounded-lg border border-gray-200 bg-white p-5 flex flex-col">
    <div class="mb-3 flex items-center justify-between">
      <span class="text-md font-medium text-gray-600">{{ $props.title }}</span>
      <Badge
        :color="badges[status].color"
        :content="badges[status].content"
        icon="dot"
        size="sm"
        shape="pill"
      />
    </div>
    <div class="mt-auto">
      <div class="flex items-baseline justify-between">
        <span class="text-display-xs font-semibold">{{ prettyCurrent }}</span>
        <span v-if="$props.total == Infinity">
          <Icon name="infinity" size="sm" class="mb-[-.4em]" stroke-color="" />
        </span>
        <span v-else class="font-medium text-sm">
          {{ prettyTotal }}
        </span>
      </div>
      <Progress v-model="progress" :class="cn('h-2', progressClass[status])" />
    </div>
  </div>
</template>
