<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

import {
  type FeaturedIconOutlineVariants,
  featuredIconOutlineVariants,
  featuredIconLayerVariants
} from '.'
import { type IconVariants } from '@/components/icon'

import { Icon } from '@/components/icon'

interface Props {
  color?: FeaturedIconOutlineVariants['color']
  size?: IconVariants['size']
  name?: string
  class?: HTMLAttributes['class']
  iconClass?: HTMLAttributes['class']
  kind: FeaturedIconOutlineVariants['kind']
}

const props = withDefaults(defineProps<Props>(), {
  kind: 'outline',
  color: 'current',
  size: 'md',
  name: undefined,
  class: undefined,
  iconClass: undefined
})

const iconMap: Record<NonNullable<Props['color']>, string> = {
  error: 'alert-circle',
  warning: 'alert-circle',
  success: 'check-circle',
  temporary: 'clock',
  persistent: 'monitor-02',
  brand: 'info-circle',
  gray: 'info-circle',
  current: 'info-circle',
  deployment: 'layout-alt-04'
}

const defaultIcon = computed(() => iconMap[props.color!])
</script>

<template>
  <div :class="cn(featuredIconOutlineVariants({ color, kind }), 'flex icon', props.class)">
    <div :class="featuredIconLayerVariants({ kind, layer: 'outer', color })">
      <div :class="featuredIconLayerVariants({ kind, layer: 'inner', color })">
        <Icon
          :name="props.name || defaultIcon"
          :size="props.size"
          :class="cn('text-current!', props.iconClass)"
        />
      </div>
    </div>
  </div>
</template>
