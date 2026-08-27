<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

import {
  getDesktopDetailsOptions,
  getDesktopDetailsFromTokenOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import type { Client } from '@/gen/oas/apiv4/client'

import { Icon, CopyIcon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import {
  CARD_SIZE_INJECTION_KEY,
  cardOverlayPaddingVariants,
  cardOverlayTextVariants,
  cardOverlayLabelVariants
} from '..'

const { t } = useI18n()

interface DesktopInfoTarget {
  id: string
  status: DesktopStatusEnum
  ip?: string | null
}

interface Props {
  desktop: DesktopInfoTarget
  // When provided, fetches the details via the direct-viewer token endpoint
  // (using the supplied client's viewer JWT). Otherwise falls back to the
  // standard user-authenticated endpoint keyed by desktopId.
  directViewerToken?: string
  directViewerClient?: Client
}

const props = withDefaults(defineProps<Props>(), {
  directViewerToken: undefined,
  directViewerClient: undefined
})
const emit = defineEmits<{ showInfoModal: [] }>()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const isDirectViewer = !!props.directViewerToken && !!props.directViewerClient
const tokenQuery = useQuery({
  ...getDesktopDetailsFromTokenOptions({
    path: { token: props.directViewerToken ?? '' },
    client: props.directViewerClient
  }),
  enabled: isDirectViewer
})

const desktopIdQuery = useQuery({
  ...getDesktopDetailsOptions({
    path: { desktop_id: props.desktop.id }
  }),
  enabled: !isDirectViewer
})

const active = computed(() => (isDirectViewer ? tokenQuery : desktopIdQuery))
const info = computed(() => active.value.data.value)

const hardware = computed(() => ({
  vcpus: info.value?.vcpu,
  memory: info.value?.memory,
  diskBus: info.value?.disk_bus?.name ?? '',
  bootOrder: info.value?.boot_order?.map((b) => b.name) ?? [],
  videos: info.value?.videos?.map((v) => v.name) ?? [],
  isos: info.value?.isos ?? [],
  floppies: info.value?.floppies ?? [],
  vgpus: info.value?.reservables?.vgpus ?? []
}))

const isPending = computed(() => active.value.isPending.value)

const desktopIp = computed(() => props.desktop.ip)

// Same affordance as the networks overlay: the guest hasn't reported its
// address yet, so an empty IP row is expected rather than missing data.
const isWaitingIp = computed(() => props.desktop.status === DesktopStatusEnum.WAITING_IP)

const statusBadge = computed(() => {
  const s = props.desktop.status
  if (s === DesktopStatusEnum.STARTED) return 'bg-success-500/80'
  if (s === DesktopStatusEnum.FAILED) return 'bg-error-500/80'
  if (s === DesktopStatusEnum.STOPPED) return 'bg-base-white/20'
  return 'bg-warning-500/70'
})

const diskBusLabel = computed(() => hardware.value.diskBus)

// Video adapters
const videoLabel = computed(() => hardware.value.videos.join(', '))

const bootOrderLabel = computed(() => hardware.value.bootOrder.join(', '))

// Reservables
const reservables = computed(() => hardware.value.vgpus)
const firstReservable = computed(() => reservables.value[0])
const hiddenReservables = computed(() => reservables.value.slice(1))
const hiddenReservablesLabel = computed(() => hiddenReservables.value.join(', '))

// Attached media
interface AttachedMedia {
  kind: 'iso' | 'floppy'
  label: string
}
const attachedMedia = computed<AttachedMedia[]>(() => {
  const isos = hardware.value.isos
  const floppies = hardware.value.floppies
  return [
    ...isos.map((m) => ({ kind: 'iso' as const, label: m.name || m.id })),
    ...floppies.map((m) => ({ kind: 'floppy' as const, label: m.name || m.id }))
  ]
})
const firstMedia = computed(() => attachedMedia.value[0])
const hiddenMedia = computed(() => attachedMedia.value.slice(1))
const hiddenMediaLabel = computed(() => hiddenMedia.value.map((m) => m.label).join(', '))

const mediaLabelRef = ref<HTMLElement | null>(null)
const { isTruncated: isMediaLabelTruncated } = useIsTextTruncated(
  mediaLabelRef,
  () => firstMedia.value?.label
)

const gpuLabelRef = ref<HTMLElement | null>(null)
const { isTruncated: isGpuLabelTruncated } = useIsTextTruncated(
  gpuLabelRef,
  () => firstReservable.value
)

const bootOrderLabelRef = ref<HTMLElement | null>(null)
const { isTruncated: isBootOrderLabelTruncated } = useIsTextTruncated(
  bootOrderLabelRef,
  () => bootOrderLabel.value
)

const diskBusLabelRef = ref<HTMLElement | null>(null)
const { isTruncated: isDiskBusLabelTruncated } = useIsTextTruncated(
  diskBusLabelRef,
  () => diskBusLabel.value
)

const desktopIpRef = ref<HTMLElement | null>(null)
const { isTruncated: isDesktopIpTruncated } = useIsTextTruncated(
  desktopIpRef,
  () => desktopIp.value
)

const videoLabelRef = ref<HTMLElement | null>(null)
const { isTruncated: isVideoLabelTruncated } = useIsTextTruncated(
  videoLabelRef,
  () => videoLabel.value
)
</script>

<template>
  <div
    :class="cardOverlayPaddingVariants({ size })"
    class="text-base-white text-start relative min-h-full flex flex-col justify-between"
  >
    <div class="flex items-center justify-between gap-2">
      <span
        class="inline-flex items-center px-1.5 py-0.5 rounded font-bold uppercase tracking-wide w-fit"
        :class="[statusBadge, cardOverlayLabelVariants({ size })]"
      >
        <span class="sr-only">{{ t('components.desktops.desktop-card.info.status') }}: </span>
        {{ desktop.status }}
      </span>

      <div
        v-if="isPending || desktopIp || isWaitingIp"
        class="flex items-center gap-1.5 min-w-0"
        :class="cardOverlayTextVariants({ size })"
      >
        <Icon
          :name="isWaitingIp ? 'loading-02' : 'signal-01'"
          size="xs"
          stroke-color="base-white"
          :class="['shrink-0', isWaitingIp && 'motion-safe:animate-spin']"
          aria-hidden="true"
        />
        <span v-if="isWaitingIp" class="italic truncate pr-0.5">
          {{ t('components.desktops.desktop-card.status.waitingip.text') }}
        </span>
        <Skeleton v-else-if="isPending && !desktopIp" class="bg-base-white/20 h-3 w-24" />
        <template v-else-if="desktopIp">
          <span class="sr-only">
            {{ t('components.desktops.desktop-card.ip-address', { ip: desktopIp }) }}
          </span>
          <Tooltip>
            <TooltipTrigger as-child>
              <code ref="desktopIpRef" aria-hidden="true" class="font-mono truncate">{{
                desktopIp
              }}</code>
            </TooltipTrigger>
            <TooltipContent v-if="isDesktopIpTruncated" :title="desktopIp" />
          </Tooltip>
          <CopyIcon :value="desktopIp" size="xs" stroke-color="base-white" class="shrink-0" />
        </template>
      </div>
    </div>

    <div
      class="flex flex-wrap items-center gap-x-4 gap-y-1"
      :class="cardOverlayTextVariants({ size })"
    >
      <div class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon name="cpu" size="xs" stroke-color="base-white" class="shrink-0" aria-hidden="true" />
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-12" />
        <span v-else class="font-semibold truncate">
          {{
            hardware.vcpus
              ? t('components.domain-info-modal.fields.hardware.vcpu', {
                  vcpu: hardware.vcpus
                })
              : '—'
          }}
        </span>
      </div>

      <div class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon
          name="memory"
          size="xs"
          stroke-color="base-white"
          class="shrink-0"
          aria-hidden="true"
        />
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-16" />
        <span v-else class="font-semibold truncate">
          {{
            hardware.memory != null
              ? t('components.domain-info-modal.fields.hardware.ram', {
                  ram: Number(hardware.memory)
                })
              : '—'
          }}
        </span>
      </div>

      <!-- Reservables (vGPU) -->
      <div
        v-if="isPending || firstReservable"
        class="flex items-center gap-1.5 min-w-0 max-w-[47%]"
      >
        <Icon name="gpu" size="xs" stroke-color="base-white" class="shrink-0" aria-hidden="true" />
        <span
          class="uppercase tracking-wide text-base-white/70 shrink-0"
          :class="cardOverlayLabelVariants({ size })"
        >
          {{ t('components.desktops.desktop-card.info.reservables') }}
        </span>
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-16" />
        <template v-else>
          <Tooltip>
            <TooltipTrigger as-child>
              <span ref="gpuLabelRef" class="font-semibold truncate">{{ firstReservable }}</span>
            </TooltipTrigger>
            <TooltipContent v-if="isGpuLabelTruncated" :title="firstReservable" />
          </Tooltip>
          <Tooltip v-if="hiddenReservables.length">
            <TooltipTrigger as-child>
              <button
                type="button"
                class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded bg-base-white/15 font-semibold"
                :class="cardOverlayLabelVariants({ size })"
                :aria-label="
                  t('components.desktops.desktop-card.info.show-more', {
                    count: hiddenReservables.length,
                    items: hiddenReservablesLabel
                  })
                "
                @click="emit('showInfoModal')"
              >
                +{{ hiddenReservables.length }}
              </button>
            </TooltipTrigger>
            <TooltipContent :title="hiddenReservablesLabel" />
          </Tooltip>
        </template>
      </div>

      <!-- Attached media (ISO / floppy) -->
      <div v-if="isPending || firstMedia" class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon
          :name="firstMedia?.kind === 'floppy' ? 'save-01' : 'disc-02'"
          size="xs"
          stroke-color="base-white"
          class="shrink-0"
          aria-hidden="true"
        />
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-20" />
        <template v-else-if="firstMedia">
          <span
            class="uppercase tracking-wide text-base-white/70 shrink-0"
            :class="cardOverlayLabelVariants({ size })"
          >
            {{
              firstMedia.kind === 'iso'
                ? t('components.desktops.desktop-card.info.iso')
                : t('components.desktops.desktop-card.info.floppy')
            }}
          </span>
          <Tooltip>
            <TooltipTrigger as-child>
              <span ref="mediaLabelRef" class="font-semibold truncate">{{ firstMedia.label }}</span>
            </TooltipTrigger>
            <TooltipContent v-if="isMediaLabelTruncated" :title="firstMedia.label" />
          </Tooltip>
          <Tooltip v-if="hiddenMedia.length">
            <TooltipTrigger as-child>
              <button
                type="button"
                class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded bg-base-white/15 font-semibold"
                :class="cardOverlayLabelVariants({ size })"
                :aria-label="
                  t('components.desktops.desktop-card.info.show-more', {
                    count: hiddenMedia.length,
                    items: hiddenMediaLabel
                  })
                "
                @click="emit('showInfoModal')"
              >
                +{{ hiddenMedia.length }}
              </button>
            </TooltipTrigger>
            <TooltipContent :title="hiddenMediaLabel" />
          </Tooltip>
        </template>
      </div>

      <!-- Boot order -->
      <div class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon name="hdd" size="xs" stroke-color="base-white" class="shrink-0" aria-hidden="true" />
        <span
          class="uppercase tracking-wide text-base-white/70 shrink-0"
          :class="cardOverlayLabelVariants({ size })"
        >
          {{ t('components.desktops.desktop-card.info.boot') }}
        </span>
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-20" />
        <Tooltip v-else>
          <TooltipTrigger as-child>
            <span ref="bootOrderLabelRef" class="font-semibold truncate">
              {{ bootOrderLabel || '—' }}
            </span>
          </TooltipTrigger>
          <TooltipContent v-if="isBootOrderLabelTruncated" :title="bootOrderLabel" />
        </Tooltip>
      </div>

      <!-- Disk bus -->
      <div v-if="isPending || diskBusLabel" class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon
          name="hdd-02"
          size="xs"
          stroke-color="base-white"
          class="shrink-0"
          aria-hidden="true"
        />
        <span
          class="uppercase tracking-wide text-base-white/70 shrink-0"
          :class="cardOverlayLabelVariants({ size })"
        >
          {{ t('components.desktops.desktop-card.info.disk-bus') }}
        </span>
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-12" />
        <Tooltip v-else>
          <TooltipTrigger as-child>
            <span ref="diskBusLabelRef" class="font-semibold truncate">{{ diskBusLabel }}</span>
          </TooltipTrigger>
          <TooltipContent v-if="isDiskBusLabelTruncated" :title="diskBusLabel" />
        </Tooltip>
      </div>

      <!-- Video adapters -->
      <div v-if="isPending || videoLabel" class="flex items-center gap-1.5 min-w-0 max-w-[47%]">
        <Icon
          name="wires"
          size="xs"
          stroke-color="base-white"
          class="shrink-0"
          aria-hidden="true"
        />
        <span
          class="uppercase tracking-wide text-base-white/70 shrink-0"
          :class="cardOverlayLabelVariants({ size })"
        >
          {{ t('components.desktops.desktop-card.info.video') }}
        </span>
        <Skeleton v-if="isPending" class="bg-base-white/20 h-3 w-16" />
        <Tooltip v-else>
          <TooltipTrigger as-child>
            <span ref="videoLabelRef" class="font-semibold truncate">{{ videoLabel }}</span>
          </TooltipTrigger>
          <TooltipContent v-if="isVideoLabelTruncated" :title="videoLabel" />
        </Tooltip>
      </div>
    </div>

    <div class="flex justify-end">
      <Tooltip>
        <TooltipTrigger as-child>
          <Button
            hierarchy="link-gray"
            size="sm"
            class="h-6! px-2! gap-1 bg-base-white/15 hover:bg-base-white/30 font-semibold text-base-white"
            :class="cardOverlayLabelVariants({ size })"
            @click="emit('showInfoModal')"
          >
            {{ t('components.desktops.desktop-card.overlay.expand') }}
            <Icon name="expand-04" size="xs" stroke-color="base-white" aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.desktops.desktop-card.overlay.expand-tooltip')" />
      </Tooltip>
    </div>
  </div>
</template>
