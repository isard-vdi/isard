<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import {
  desktopStatusIsTransitional,
  desktopStatusLabel,
  desktopStatusTone,
  type DesktopStatusTone
} from '@/lib/desktops'
import { cn, startCase } from '@/lib/utils'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import Badge from '@/components/badge/Badge.vue'
import { CopyIcon } from '@/components/icon'

const i18n = useI18n()
const { t } = i18n

interface Props {
  desktop: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {})

const STATUS_BADGE_COLOR: Record<DesktopStatusTone, 'green' | 'red' | 'gray' | 'lightyellow'> = {
  success: 'green',
  error: 'red',
  neutral: 'gray',
  warning: 'lightyellow'
}

const statusColor = computed(() => STATUS_BADGE_COLOR[desktopStatusTone(props.desktop.status)])

const statusLabel = computed(() => desktopStatusLabel(props.desktop.status, i18n))

const isTransitional = computed(() => desktopStatusIsTransitional(props.desktop.status))
</script>

<template>
  <div class="flex min-w-0 flex-row items-center gap-1.5 select-none">
    <!-- Keyed on the status so each change remounts the badge and fades the new
         one in; opacity only, inside a box the row already reserves. -->
    <Badge
      :key="props.desktop.status"
      :color="statusColor"
      :content="statusLabel"
      :icon="isTransitional ? 'loading-02' : undefined"
      shape="square"
      size="sm"
      :class="
        cn(
          'font-semibold shrink-0',
          'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300',
          isTransitional && 'gap-1.5 [&_svg]:text-warning-800! motion-safe:[&_svg]:animate-spin'
        )
      "
    />

    <div
      v-if="props.desktop.ip"
      class="flex shrink-0 flex-row items-center gap-1 text-muted-foreground text-xs"
    >
      <Tooltip>
        <TooltipTrigger as-child>
          <p>{{ props.desktop.ip }}</p>
        </TooltipTrigger>
        <TooltipContent :title="startCase(t(`components.desktops.fields.ip.title-full`))">
        </TooltipContent>
      </Tooltip>

      <CopyIcon :value="props.desktop.ip" size="xs" stroke-color="currentColor" />
    </div>
  </div>
</template>
