<script setup lang="ts">
import { computed } from 'vue'
import Icon from '@/components/icon/Icon.vue'
import { cn } from '@/lib/utils'

interface Props {
  open?: boolean
  icon?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  icon: undefined,
  class: ''
})

const emit = defineEmits(['click'])

const buttonClasses = computed(() =>
  cn(
    'w-12 h-12 p-2 rounded-md flex items-center justify-center overflow-hidden transition-colors duration-150',
    'bg-base-menu hover:bg-base-menu-hover',
    'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[rgba(179,170,152,0.14)]'
  )
)

const iconName = computed(() => props.icon ?? (props.open ? 'align-left-01' : 'align-right-01'))

const iconColor = computed(() => 'gray-warm-700')
</script>

<template>
  <button :class="cn(buttonClasses, props.class)" @click="emit('click', $event)">
    <Icon :name="iconName" size="lg" :stroke-color="iconColor" />
  </button>
</template>
