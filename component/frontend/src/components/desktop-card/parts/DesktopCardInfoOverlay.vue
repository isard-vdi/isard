<script setup lang="ts">
import { computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { getDesktopInfoOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { UserDesktop } from '@/gen/oas/apiv4/'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Icon, CopyIcon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import { CARD_SIZE_INJECTION_KEY, cardOverlayPaddingVariants } from '..'

const { t } = useI18n()

interface Props {
  desktop: UserDesktop
}

const props = defineProps<Props>()
const emit = defineEmits<{ showInfoModal: [] }>()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const { data: info, isPending } = useQuery(
  getDesktopInfoOptions({
    path: { desktop_id: props.desktop.id }
  })
)

const statusBadge = computed(() => {
  const s = props.desktop.status
  if (s === DesktopStatusEnum.STARTED) return 'bg-success-500/80'
  if (s === DesktopStatusEnum.FAILED) return 'bg-error-500/80'
  if (s === DesktopStatusEnum.STOPPED) return 'bg-base-white/20'
  return 'bg-warning-500/70'
})

// Boot device labels — short, lowercase, comma-joined for the card. The
// modal shows the full per-device names; here we only need a glance.
const bootOrderLabel = computed(() => {
  const order = info.value?.hardware?.boot_order
  if (!order || !order.length) return ''
  return order.join(' → ')
})

// Attached media — combine ISOs and floppies into one list of (icon, name)
// rows. apiv4 returns enriched {id, name?} objects; fall back to id when
// name is missing so we don't render blanks.
interface AttachedMedia {
  kind: 'iso' | 'floppy'
  label: string
}
const attachedMedia = computed<AttachedMedia[]>(() => {
  const isos = info.value?.hardware?.isos ?? []
  const floppies = info.value?.hardware?.floppies ?? []
  return [
    ...isos.map((m) => ({ kind: 'iso' as const, label: m.name || m.id })),
    ...floppies.map((m) => ({ kind: 'floppy' as const, label: m.name || m.id }))
  ]
})
</script>

<template>
  <div :class="cardOverlayPaddingVariants({ size })" class="text-base-white text-start">
    <div class="flex items-center gap-2 mb-1.5">
      <Icon name="info-circle" size="sm" stroke-color="base-white" />
      <span class="text-[10px] font-bold uppercase tracking-wide truncate">
        {{ t('components.desktops.desktop-card.actions.info') }}
      </span>
      <span
        class="ml-auto inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide"
        :class="statusBadge"
      >
        {{ desktop.status }}
      </span>
    </div>

    <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
      <div class="flex items-center gap-1.5 min-w-0">
        <Icon name="cpu" size="xs" stroke-color="base-white" class="shrink-0" />
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-12" />
        <span v-else class="font-semibold truncate">
          {{
            info?.hardware?.vcpus
              ? t('components.domain-info-modal.fields.hardware.vcpu', {
                  vcpu: info.hardware.vcpus
                })
              : '—'
          }}
        </span>
      </div>
      <div class="flex items-center gap-1.5 min-w-0">
        <Icon name="memory" size="xs" stroke-color="base-white" class="shrink-0" />
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-16" />
        <span v-else class="font-semibold truncate">
          {{
            info?.hardware?.memory != null
              ? t('components.domain-info-modal.fields.hardware.ram', {
                  ram: Number(info.hardware.memory).toFixed(2)
                })
              : '—'
          }}
        </span>
      </div>
      <div v-if="desktop.ip" class="flex items-center gap-1.5 w-fit">
        <Icon name="signal-01" size="xs" stroke-color="base-white" class="shrink-0" />
        <code class="font-mono truncate flex-1 min-w-0">{{ desktop.ip }}</code>
        <CopyIcon :value="desktop.ip" size="xs" stroke-color="base-white" class="shrink-0 ml-2" />
      </div>

      <!-- Boot order (always shown; falls back to em-dash while loading or if absent) -->
      <div class="flex items-center gap-1.5 min-w-0 col-span-2">
        <Icon name="hdd" size="xs" stroke-color="base-white" class="shrink-0" />
        <span class="text-[10px] uppercase tracking-wide text-base-white/70 shrink-0">
          {{ t('components.desktops.desktop-card.info.boot') }}
        </span>
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-20" />
        <span v-else class="font-semibold truncate">{{ bootOrderLabel || '—' }}</span>
      </div>

      <!-- Attached media — only renders when at least one is attached so
           the overlay stays compact for the common no-media case. -->
      <template v-if="attachedMedia.length">
        <div
          v-for="m in attachedMedia"
          :key="`${m.kind}:${m.label}`"
          class="flex items-center gap-1.5 min-w-0 col-span-2"
        >
          <Icon
            :name="m.kind === 'iso' ? 'disc-02' : 'save-01'"
            size="xs"
            stroke-color="base-white"
            class="shrink-0"
          />
          <span class="font-semibold truncate">{{ m.label }}</span>
        </div>
      </template>
    </div>

    <div class="flex justify-end mt-1.5">
      <Tooltip>
        <TooltipTrigger as-child>
          <Button
            hierarchy="link-gray"
            size="sm"
            class="h-6! px-2! gap-1 bg-base-white/15 hover:bg-base-white/30 text-[10px] font-semibold text-base-white"
            @click="emit('showInfoModal')"
          >
            {{ t('components.desktops.desktop-card.overlay.expand') }}
            <Icon name="expand-04" size="xs" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.desktops.desktop-card.overlay.expand-tooltip')" />
      </Tooltip>
    </div>
  </div>
</template>
