<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

import { InputField } from '@/components/input-field'
import { Kbd } from '@/components/kbd'
import { useSearchShortcuts } from '@/composables/useSearchShortcuts'

const props = defineProps<{
  id: string
  placeholder: string
  class?: HTMLAttributes['class']
}>()

const model = defineModel<string>({ default: '' })

useSearchShortcuts(() => props.id)
</script>

<template>
  <InputField
    :id="props.id"
    v-model="model"
    :placeholder="props.placeholder"
    icon="search-lg"
    :class="cn('h-full w-full min-w-0 max-w-120', props.class)"
  >
    <template #inline-end>
      <Kbd class="max-sm:hidden">/</Kbd>
    </template>
  </InputField>
</template>
