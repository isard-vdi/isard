<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Grid2x2, Grid3x3, Square } from 'lucide-vue-next'

import { cn } from '@/lib/utils'

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { PRESSED_NEUTRAL, TOGGLE_GROUP, TOGGLE_ITEM, type MosaicDensity } from '../constants'

const density = defineModel<MosaicDensity>({ required: true })

const { t } = useI18n()

const DENSITIES = [
  { value: 'lg', icon: Square },
  { value: 'md', icon: Grid2x2 },
  { value: 'sm', icon: Grid3x3 }
] as const

const change = (value: string | string[]) => {
  if (value === 'lg' || value === 'md' || value === 'sm') density.value = value
}
</script>

<template>
  <ToggleGroup
    :model-value="density"
    type="single"
    :spacing="1"
    :aria-label="t('views.deployment-videowall.viewer.density.label')"
    :class="TOGGLE_GROUP"
    @update:model-value="change"
  >
    <Tooltip v-for="option in DENSITIES" :key="option.value">
      <TooltipTrigger as-child>
        <ToggleGroupItem
          :value="option.value"
          :aria-label="t(`views.deployment-videowall.viewer.density.${option.value}`)"
          :class="cn(TOGGLE_ITEM, PRESSED_NEUTRAL, 'w-8 px-0')"
        >
          <component :is="option.icon" />
        </ToggleGroupItem>
      </TooltipTrigger>
      <TooltipContent :title="t(`views.deployment-videowall.viewer.density.${option.value}`)" />
    </Tooltip>
  </ToggleGroup>
</template>
