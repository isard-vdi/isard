<script lang="ts" setup>
import { Icon } from '@/components/icon'

interface Props {
  title: string
  success?: boolean
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  success: true,
  description: undefined
})
</script>

<template>
  <div class="flex flex-col items-start justify-start">
    <div class="flex flex-row items-center justify-start gap-4">
      <Icon :name="props.success ? 'check' : 'x-close'" class="w-6" />
      <h4 class="font-semibold text-lg">
        {{ props.title }}
      </h4>
    </div>
    <p v-if="props.description" class="ml-10">
      {{ description }}
    </p>
  </div>
</template>
