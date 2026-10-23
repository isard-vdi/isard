<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Eye, MousePointerClick } from 'lucide-vue-next'

import { cn } from '@/lib/utils'

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import {
  PRESSED_AMBER,
  PRESSED_NEUTRAL,
  TOGGLE_GROUP,
  TOGGLE_ITEM,
  type ViewerMode
} from '../constants'

interface Props {
  mode: ViewerMode
  /** Watch-only no matter the mode, as in the mosaic. */
  locked: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{ change: [mode: ViewerMode] }>()

const { t } = useI18n()

const MODES = [
  { value: 'view', icon: Eye, pressed: PRESSED_NEUTRAL },
  { value: 'control', icon: MousePointerClick, pressed: PRESSED_AMBER }
] as const

const change = (value: string | string[]) => {
  if (value === 'view' || value === 'control') emit('change', value)
}
</script>

<template>
  <!-- Disabled items take no pointer events: the span keeps the locked tooltip. -->
  <Tooltip :disabled="!props.locked">
    <TooltipTrigger as-child>
      <span class="inline-flex shrink-0">
        <ToggleGroup
          :model-value="props.locked ? 'view' : props.mode"
          type="single"
          :spacing="1"
          :disabled="props.locked"
          :aria-label="t('views.deployment-videowall.viewer.mode.label')"
          :class="TOGGLE_GROUP"
          @update:model-value="change"
        >
          <Tooltip v-for="option in MODES" :key="option.value">
            <TooltipTrigger as-child>
              <ToggleGroupItem :value="option.value" :class="cn(TOGGLE_ITEM, option.pressed)">
                <component :is="option.icon" />
                {{ t(`views.deployment-videowall.viewer.mode.${option.value}`) }}
              </ToggleGroupItem>
            </TooltipTrigger>
            <TooltipContent
              :title="t(`views.deployment-videowall.viewer.mode.${option.value}-hint`)"
            />
          </Tooltip>
        </ToggleGroup>
      </span>
    </TooltipTrigger>
    <TooltipContent :title="t('views.deployment-videowall.viewer.mosaic.control-disabled')" />
  </Tooltip>
</template>
