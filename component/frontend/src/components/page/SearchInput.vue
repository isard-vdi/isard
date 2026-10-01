<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

import { InputField } from '@/components/input-field'
import { Kbd } from '@/components/kbd'
import { useSearchShortcuts } from '@/composables/useSearchShortcuts'
import { vAutofocus } from '@/directives/autofocus'

const props = defineProps<{
  id: string
  placeholder: string
  class?: HTMLAttributes['class']
  autofocus?: boolean
}>()

const model = defineModel<string>({ default: '' })

useSearchShortcuts(() => props.id)
</script>

<template>
  <InputField
    :id="props.id"
    v-model="model"
    v-autofocus="props.autofocus"
    :placeholder="props.placeholder"
    :aria-label="props.placeholder"
    icon="search-lg"
    :class="cn('h-full w-full min-w-0 max-w-80', props.class)"
  >
    <template #inline-end>
      <Kbd class="max-sm:hidden">/</Kbd>
    </template>
  </InputField>
</template>
