<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { CopyIcon, Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import type { DesktopTemplate } from '@/gen/oas/apiv4'
import Badge from '@/components/badge/Badge.vue'
import { hasWireguardRequiringViewer } from '@/lib/viewers'

const { t } = useI18n()

export interface Props {
  domainId?: string
  name: string
  description?: string
  status?: string
  ip?: string | null
  vcpu?: number
  ram?: number
  bootOrder?: string[]
  diskBus?: string
  vga?: string[]
  viewers?: string[]
  fullscreen?: boolean
  isos?: string[]
  floppies?: string[]
  reservables?: string[] | null
  credentials?: { username?: string | null; password?: string | null } | null
  kind: 'desktop' | 'template'
  template?: DesktopTemplate | null
  showId?: boolean
  desktopKind?: 'persistent' | 'nonpersistent' | 'deployment' | null
}

const props = withDefaults(defineProps<Props>(), {
  domainId: '-',
  description: undefined,
  status: 'Unknown',
  ip: undefined,
  vcpu: undefined,
  ram: undefined,
  bootOrder: undefined,
  diskBus: undefined,
  vga: undefined,
  viewers: undefined,
  fullscreen: undefined,
  isos: undefined,
  floppies: undefined,
  reservables: undefined,
  credentials: undefined,
  showId: false,
  desktopKind: undefined
})

const showCredentials = computed(
  () =>
    hasWireguardRequiringViewer(props.viewers ?? []) &&
    !!(props.credentials?.username || props.credentials?.password)
)

const hasBothCredentials = computed(
  () => !!(props.credentials?.username && props.credentials?.password)
)

const tintBgClass = computed(() => {
  if (props.kind !== 'desktop') return 'bg-brand-100/40'
  if (props.desktopKind === 'persistent') return 'bg-secondary-3-500/15'
  if (props.desktopKind === 'nonpersistent') return 'bg-secondary-1-500/15'
  if (props.desktopKind === 'deployment') return 'bg-secondary-2-500/15'
  return 'bg-brand-100/40'
})

const hasHardware = computed(
  () =>
    props.vcpu != null || props.ram != null || !!props.bootOrder || !!props.diskBus || !!props.vga
)
const hasViewers = computed(
  () => !!(props.viewers && props.viewers.length > 0) || props.fullscreen != null
)
const hasPeripherals = computed(
  () => !!(props.isos && props.isos.length > 0) || !!(props.floppies && props.floppies.length > 0)
)
const hasReservables = computed(() => !!props.reservables?.length)

type GridSectionKey = 'hardware' | 'viewers' | 'peripherals' | 'reservables'

const gridSections = computed<GridSectionKey[]>(() => {
  const sections: GridSectionKey[] = []
  if (hasHardware.value) sections.push('hardware')
  if (hasViewers.value) sections.push('viewers')
  if (hasPeripherals.value) sections.push('peripherals')
  if (hasReservables.value) sections.push('reservables')
  return sections
})

const showRow1Divider = computed(() => gridSections.value.length >= 2)
const showRow2Divider = computed(() => gridSections.value.length >= 4)

const showRowDivider = computed(() => gridSections.value.length > 2)

const gridSectionSpanClass = (key: GridSectionKey): string => {
  const sections = gridSections.value
  const isLast = sections[sections.length - 1] === key
  const isOddCount = sections.length % 2 === 1
  return isLast && isOddCount ? 'col-span-2' : ''
}

const gridSectionOrder = (key: GridSectionKey): number => {
  const index = gridSections.value.indexOf(key)
  if (index === -1) return 0
  return index < 2 ? index : index + 1
}
</script>

<template>
  <div class="flex flex-col gap-3 text-gray-warm-700">
    <!-- Template and Desktop ID -->
    <div
      v-if="showId"
      :class="props.template ? 'grid grid-cols-2 gap-6' : 'grid grid-cols-1'"
      class="relative"
    >
      <div v-if="props.template" class="flex gap-1.5 w-full min-w-0 items-center">
        <span class="text-[10px] font-bold text-brand-700 uppercase tracking-wide shrink-0">
          {{ t(`components.domain-info-modal.${props.kind}.fields.template.id`) }}
        </span>
        <div
          class="flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 min-w-0 flex-1"
          :class="tintBgClass"
        >
          <Tooltip>
            <TooltipTrigger as-child>
              <span
                tabindex="0"
                class="text-sm truncate min-w-0 rounded-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >{{ props.template?.id }}</span
              >
            </TooltipTrigger>
            <TooltipContent :title="props.template?.id || ''" side="top" />
          </Tooltip>
          <CopyIcon :value="props.template?.id || ''" size="md" stroke-color="gray-warm-600" />
        </div>
      </div>
      <Separator
        v-if="props.template"
        orientation="vertical"
        class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
      />
      <div class="flex gap-1.5 w-full min-w-0 items-center">
        <span class="text-[10px] font-bold text-brand-700 uppercase tracking-wide shrink-0">
          {{ t(`components.domain-info-modal.${props.kind}.fields.id`) }}
        </span>
        <div
          class="flex items-center justify-between max-w-fit gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 min-w-0 flex-1"
          :class="tintBgClass"
        >
          <Tooltip>
            <TooltipTrigger as-child>
              <span
                tabindex="0"
                class="text-sm truncate min-w-0 rounded-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >{{ props.domainId }}</span
              >
            </TooltipTrigger>
            <TooltipContent :title="props.domainId || ''" side="top" />
          </Tooltip>
          <CopyIcon :value="props.domainId || ''" size="md" stroke-color="gray-warm-600" />
        </div>
      </div>
      <Separator class="absolute -bottom-2" />
    </div>

    <div
      class="flex flex-col divide-y divide-gray-warm-200 [&>*]:py-3 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0"
    >
      <div
        v-if="props.template || props.description || props.ip || showCredentials"
        class="flex flex-col gap-2"
      >
        <dl class="grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-3">
          <template v-if="props.template">
            <dt class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t(`components.domain-info-modal.${props.kind}.fields.template.title`) }}
            </dt>
            <dd class="m-0 min-w-0 text-sm font-regular">{{ props.template?.name }}</dd>
          </template>
          <template v-if="props.description">
            <dt class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.description.title') }}
            </dt>
            <dd class="m-0 min-w-0 text-sm font-regular">{{ props.description }}</dd>
          </template>
          <template v-if="showCredentials">
            <dt class="self-center text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.credentials.title') }}
            </dt>
            <dd class="m-0 min-w-0 self-center text-sm font-regular">
              <div class="flex gap-4">
                <div
                  v-if="props.credentials?.username"
                  class="flex items-center gap-1.5 min-w-0"
                  :class="hasBothCredentials ? 'max-w-[50%]' : ''"
                >
                  <Icon name="user-03" size="md" stroke-color="gray-warm-700" class="shrink-0" />
                  <div
                    class="flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 min-w-0"
                    :class="tintBgClass"
                  >
                    <span class="text-sm truncate min-w-0">{{ props.credentials.username }}</span>
                    <CopyIcon
                      :value="props.credentials.username"
                      size="md"
                      stroke-color="gray-warm-600"
                    />
                  </div>
                </div>
                <Separator
                  v-if="props.credentials?.username && props.credentials?.password"
                  orientation="vertical"
                  class="h-auto"
                />
                <div
                  v-if="props.credentials?.password"
                  class="flex items-center gap-1.5 min-w-0"
                  :class="hasBothCredentials ? 'max-w-[50%]' : ''"
                >
                  <Icon
                    name="passcode-lock"
                    size="md"
                    stroke-color="gray-warm-700"
                    class="shrink-0"
                  />
                  <div
                    class="flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 min-w-0"
                    :class="tintBgClass"
                  >
                    <span class="text-sm truncate min-w-0">{{ props.credentials.password }}</span>
                    <CopyIcon
                      :value="props.credentials.password"
                      size="md"
                      stroke-color="gray-warm-600"
                    />
                  </div>
                </div>
              </div>
            </dd>
          </template>
          <template v-if="props.ip">
            <dt class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.ip.title') }}
            </dt>
            <dd
              class="m-0 min-w-0 max-w-fit flex items-center gap-2.5 shadow-xs px-2 py-1 rounded-lg border border-gray-warm-200 text-sm font-regular"
              :class="tintBgClass"
            >
              <Tooltip>
                <TooltipTrigger as-child>
                  <span
                    tabindex="0"
                    class="truncate min-w-0 rounded-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >{{ props.ip }}</span
                  >
                </TooltipTrigger>
                <TooltipContent :title="props.ip || ''" side="top" />
              </Tooltip>
              <CopyIcon :value="props.ip" size="md" stroke-color="gray-warm-600" />
            </dd>
          </template>
        </dl>
      </div>

      <div class="relative grid grid-cols-2 gap-x-6 gap-y-4">
        <Separator
          v-if="showRow1Divider"
          orientation="vertical"
          class="absolute top-0 left-1/2 -translate-x-1/2 [grid-row:1/2] [grid-column:1/3]"
        />
        <Separator
          v-if="showRow2Divider"
          orientation="vertical"
          class="absolute top-0 left-1/2 -translate-x-1/2 [grid-row:3/4] [grid-column:1/3]"
        />
        <Separator v-if="showRowDivider" class="col-span-2" style="order: 2" />

        <!-- Hardware -->
        <div
          v-if="hasHardware"
          class="flex flex-col gap-1.5"
          :class="gridSectionSpanClass('hardware')"
          :style="{ order: gridSectionOrder('hardware') }"
        >
          <div class="flex items-center gap-1.5">
            <Icon name="cpu" size="md" stroke-color="brand-700" />
            <h4 class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.hardware.title') }}
            </h4>
          </div>
          <div class="flex flex-wrap gap-1.5" role="list">
            <Badge
              v-if="props.vcpu != null"
              :content="
                t('components.domain-info-modal.fields.hardware.vcpu', { vcpu: props.vcpu })
              "
              icon="cpu"
              color="gray"
              shape="square"
              size="sm"
              class="gap-1.5"
              role="listitem"
            />
            <Badge
              v-if="props.ram != null"
              :content="
                t('components.domain-info-modal.fields.hardware.ram', {
                  ram: props.ram?.toFixed(2)
                })
              "
              icon="memory"
              color="gray"
              shape="square"
              size="sm"
              class="gap-1.5"
              role="listitem"
            />
            <Tooltip v-if="props.bootOrder">
              <TooltipTrigger as-child>
                <Badge
                  :content="props.bootOrder.join(', ')"
                  icon="hdd"
                  color="gray"
                  shape="square"
                  size="sm"
                  class="gap-1.5"
                  role="listitem"
                  tabindex="0"
                />
              </TooltipTrigger>
              <TooltipContent
                :title="t('components.domain.hardware.boot-order.label')"
                side="top"
              />
            </Tooltip>
            <Tooltip v-if="props.diskBus">
              <TooltipTrigger as-child>
                <Badge
                  :content="props.diskBus"
                  icon="hdd-02"
                  color="gray"
                  shape="square"
                  size="sm"
                  class="gap-1.5"
                  role="listitem"
                  tabindex="0"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('components.domain.hardware.disk-bus.label')" side="top" />
            </Tooltip>
            <Tooltip v-if="props.vga">
              <TooltipTrigger as-child>
                <Badge
                  :content="props.vga.join(', ')"
                  icon="wires"
                  color="gray"
                  shape="square"
                  size="sm"
                  class="gap-1.5"
                  role="listitem"
                  tabindex="0"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('components.domain.hardware.videos.label')" side="top" />
            </Tooltip>
          </div>
        </div>

        <!-- Viewers -->
        <div
          v-if="hasViewers"
          class="flex flex-col gap-1.5"
          :class="gridSectionSpanClass('viewers')"
          :style="{ order: gridSectionOrder('viewers') }"
        >
          <div class="flex items-center gap-1.5">
            <Icon name="monitor" size="md" stroke-color="brand-700" class="shrink-0" />
            <h4 class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.viewers.title') }}
            </h4>
          </div>
          <div class="flex flex-col gap-1.5">
            <div class="flex flex-wrap gap-1.5" role="list">
              <Badge
                v-for="viewer in props.viewers"
                :key="viewer"
                :content="t(`viewers.${viewer.toLowerCase().replace('_', '-')}`)"
                color="gray"
                shape="square"
                size="sm"
                role="listitem"
              />
              <Badge
                v-if="props.fullscreen != null"
                :content="
                  props.fullscreen
                    ? t('components.domain-info-modal.fields.viewers.fullscreen-enabled')
                    : t('components.domain-info-modal.fields.viewers.fullscreen-disabled')
                "
                color="gray"
                shape="square"
                size="sm"
                class="w-fit"
                role="listitem"
              />
            </div>
          </div>
        </div>

        <!-- Peripherals/ISOs -->
        <div
          v-if="hasPeripherals"
          class="flex flex-col gap-1.5"
          :class="gridSectionSpanClass('peripherals')"
          :style="{ order: gridSectionOrder('peripherals') }"
        >
          <div class="flex items-center gap-1.5">
            <Icon name="disc-02" size="md" stroke-color="brand-700" class="shrink-0" />
            <h4 class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.peripherals.title') }}
            </h4>
          </div>
          <div class="flex flex-wrap gap-1.5" role="list">
            <Badge
              v-for="iso in props.isos"
              :key="iso"
              :content="iso"
              color="gray"
              shape="square"
              size="sm"
              class="max-w-full break-all"
              role="listitem"
            />
            <Badge
              v-for="floppy in props.floppies"
              :key="floppy"
              :content="floppy"
              color="gray"
              shape="square"
              size="sm"
              class="max-w-full break-all"
              role="listitem"
            />
          </div>
        </div>

        <!-- Reservables (e.g. vGPU profiles) -->
        <div
          v-if="hasReservables"
          class="flex flex-col gap-1.5"
          :class="gridSectionSpanClass('reservables')"
          :style="{ order: gridSectionOrder('reservables') }"
        >
          <div class="flex items-center gap-1.5">
            <Icon name="gpu" size="md" stroke-color="brand-700" class="shrink-0" />
            <h4 class="text-xs font-bold text-brand-700 uppercase tracking-wide">
              {{ t('components.domain-info-modal.fields.reservables.title') }}
            </h4>
          </div>
          <div class="flex flex-wrap gap-1.5" role="list">
            <Badge
              v-for="vgpu in props.reservables"
              :key="vgpu"
              :content="vgpu"
              color="gray"
              shape="square"
              size="sm"
              role="listitem"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
