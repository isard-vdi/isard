<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { useIsTextTruncated } from '@/composables/useIsTextTruncated'

import { getDesktopInfoOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DesktopDetailsResponse } from '@/gen/oas/apiv4/'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

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
  directViewer?: boolean
  directViewerDetails?: DesktopDetailsResponse | null
  directViewerDetailsPending?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  directViewer: false,
  directViewerDetails: undefined,
  directViewerDetailsPending: false
})
const emit = defineEmits<{ showInfoModal: [] }>()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const isDirectViewer = computed(() => props.directViewer)

const { data: info, isPending: isInfoPending } = useQuery({
  ...getDesktopInfoOptions({
    path: { desktop_id: props.desktop.id }
  }),
  enabled: computed(() => !isDirectViewer.value)
})

const hardware = computed(() => {
  if (isDirectViewer.value) {
    const details = props.directViewerDetails
    return {
      vcpus: details?.vcpu,
      memory: details?.memory,
      diskBus: details?.disk_bus ?? '',
      bootOrder: details?.boot_order?.map((b) => b.id) ?? [],
      videos: details?.videos?.map((v) => v.id) ?? [],
      isos: details?.isos ?? [],
      floppies: details?.floppies ?? [],
      vgpus: details?.reservables?.vgpus ?? []
    }
  }
  return {
    vcpus: info.value?.hardware?.vcpus,
    memory: info.value?.hardware?.memory,
    diskBus: info.value?.hardware?.disk_bus ?? '',
    bootOrder: info.value?.hardware?.boot_order ?? [],
    videos: info.value?.hardware?.videos ?? [],
    isos: info.value?.hardware?.isos ?? [],
    floppies: info.value?.hardware?.floppies ?? [],
    vgpus: info.value?.reservables?.vgpus ?? []
  }
})

const isPending = computed(() =>
  isDirectViewer.value ? !!props.directViewerDetailsPending : isInfoPending.value
)

// get-info (non-direct-viewer) doesn't expose the desktop's live IP on
// `desktop`, but the direct-viewer's separately-fetched details do.
const desktopIp = computed(() =>
  isDirectViewer.value ? props.directViewerDetails?.ip : props.desktop.ip
)

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
        v-if="isPending || desktopIp"
        class="flex items-center gap-1.5 min-w-0"
        :class="cardOverlayTextVariants({ size })"
      >
        <Icon
          name="signal-01"
          size="xs"
          stroke-color="base-white"
          class="shrink-0"
          aria-hidden="true"
        />
        <Skeleton v-if="isPending && !desktopIp" class="bg-base-white/20 h-3 w-24" />
        <template v-else-if="desktopIp">
          <span class="sr-only">
            {{ t('components.desktops.desktop-card.ip-address', { ip: desktopIp }) }}
          </span>
          <code aria-hidden="true" class="font-mono truncate">{{ desktopIp }}</code>
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
