<script setup lang="ts">
import { type PrimitiveProps } from 'radix-vue'
import { Icon } from '@/components/icon'
import { withDefaults, defineProps, defineEmits } from 'vue'

interface Props extends PrimitiveProps {
  icon?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  as: 'div'
})

const emit = defineEmits(['click'])
</script>

<template>
  <div
    class="flex flex-col items-center justify-center bg-base-white shadow-md rounded-lg p-4 border border-gray-warm-300"
    @click="emit('click')"
  >
    <Icon
      v-if="props.icon && !props.loading"
      :name="props.icon"
      class="w-[48px] h-[48px] fill-gray-warm-500"
    />
    <div v-if="props.loading" class="loader"></div>
    <slot v-else />
  </div>
</template>
