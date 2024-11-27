<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import CardBox from '@/components/card-box/CardBox.vue'

interface Props {
  title: string
  count: number
  colorClass: string
  icon?: string
}

const props = defineProps<Props>()

const emit = defineEmits(['click'])
</script>

<template>
  <div>
    <CardBox :icon="props.icon" @click="emit('click')">
      <p class="text-lg font-semibold text-gray-900">{{ props.title }}</p>
      <p :class="['text-2xl font-bold', props.colorClass]">{{ props.count }}</p>
    </CardBox>
  </div>
</template>
