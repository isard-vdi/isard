<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import { EMPTY_STATE_IMAGES, type EmptyStateKind } from './empty-state'

const props = withDefaults(
  defineProps<{
    // Resolves the illustration and the default copy. Omit it for a placeholder
    // that is not a resource list, and pass `title` instead.
    kind?: EmptyStateKind
    // `first-run` teaches what the resource is; `no-results` only offers a way back.
    variant?: 'first-run' | 'no-results'
    title?: string
    description?: string
    searching?: boolean
    activeFilters?: number
    class?: HTMLAttributes['class']
  }>(),
  {
    kind: undefined,
    variant: 'first-run',
    title: undefined,
    description: undefined,
    activeFilters: 0,
    class: undefined
  }
)

const emit = defineEmits<{ clearSearch: []; clearFilters: [] }>()

const { t } = useI18n()

const isFirstRun = computed(() => props.variant === 'first-run')

const image = computed(() => (props.kind ? EMPTY_STATE_IMAGES[props.kind] : undefined))

const kindKey = (field: 'title' | 'description') =>
  props.kind ? t(`components.empty.${props.kind}.${field}`) : ''

const title = computed(
  () => props.title ?? (isFirstRun.value ? kindKey('title') : t('components.empty-search.title'))
)

const description = computed(
  () =>
    props.description ??
    (isFirstRun.value ? kindKey('description') : t('components.empty-search.description'))
)
</script>

<template>
  <Empty :class="cn('min-h-80 justify-center gap-6 py-8', props.class)">
    <EmptyHeader class="max-w-2xl gap-3">
      <EmptyMedia v-if="image" variant="default" class="pointer-events-none select-none">
        <!-- Shrinks with the viewport so the call to action never scrolls out of reach. -->
        <img
          :src="image"
          alt=""
          aria-hidden="true"
          :class="
            cn(
              'w-auto max-w-full object-contain',
              isFirstRun ? 'max-h-[34svh] min-h-30' : 'max-h-[22svh] min-h-24'
            )
          "
        />
      </EmptyMedia>
      <EmptyTitle
        :class="
          cn(
            'font-bold text-gray-warm-900',
            isFirstRun ? 'text-display-sm md:text-display-md' : 'text-display-xs md:text-display-sm'
          )
        "
      >
        {{ title }}
      </EmptyTitle>
      <EmptyDescription v-if="description" class="text-md text-gray-warm-600">
        {{ description }}
      </EmptyDescription>
    </EmptyHeader>

    <slot />

    <EmptyContent v-if="!isFirstRun && (props.searching || props.activeFilters)" class="flex-row">
      <Button
        v-if="props.searching"
        hierarchy="secondary-gray"
        icon="x-close"
        @click="emit('clearSearch')"
      >
        {{ t('components.empty-search.clear') }}
      </Button>
      <Button
        v-if="props.activeFilters"
        hierarchy="secondary-gray"
        icon="filter-funnel-02"
        @click="emit('clearFilters')"
      >
        {{ t('components.empty.clear-filters') }}
      </Button>
    </EmptyContent>

    <EmptyContent v-if="$slots.actions" class="max-w-none flex-row flex-wrap justify-center">
      <slot name="actions" />
    </EmptyContent>
  </Empty>
</template>
