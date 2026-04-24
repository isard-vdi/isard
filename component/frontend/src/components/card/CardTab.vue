<script setup lang="ts">
import { Icon } from '@/components/icon'
import { computed } from 'vue'

const props = defineProps<{
  kind?: 'persistent' | 'volatile' | 'deployment' | 'lab'
}>()

const variant = computed(() => {
  const variants = {
    persistent: {
      bgColor: 'var(--secondary-3-500)',
      iconColor: 'var(--secondary-3-600)',
      icon: 'browser'
    },
    volatile: {
      bgColor: 'var(--secondary-1-500)',
      iconColor: 'var(--secondary-1-600)',

      icon: 'clock'
    },
    deployment: {
      bgColor: 'var(--secondary-2-500)',
      iconColor: 'var(--secondary-2-600)',

      icon: 'layout-alt-04'
    },
    lab: {
      bgColor: 'var(--labs-200)',
      iconColor: 'var(--labs-300)',

      icon: 'beaker-02'
    }
  }

  return variants[props.kind || 'persistent']
})
const icon = computed(() => variant.value.icon)
const bgColor = computed(() => variant.value['bgColor'])
const iconColor = computed(() => variant.value['iconColor'])
</script>

<template>
  <div class="absolute top-0 left-0 h-full w-[50px] z-10 flex flex-col">
    <div
      class="w-[50px] h-[50px] rounded-br-[30px] rounded-tl-[0px] flex items-center justify-center"
      :style="{ backgroundColor: bgColor }"
    >
      <Icon :name="icon" :stroke-color="iconColor" />
    </div>

    <div class="grow w-[11px] -mt-1 rounded-bl-[30px]" :style="{ backgroundColor: bgColor }" />
  </div>
</template>
