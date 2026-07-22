<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { CopyIcon, Icon } from '@/components/icon'
import type { DesktopTemplate } from '@/gen/oas/apiv4'
import Badge from '@/components/badge/Badge.vue'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

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
  kind: 'desktop' | 'template'
  template?: DesktopTemplate | null
  showId?: boolean
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
  showId: false
})

const statusBadgeColor = computed<'green' | 'gray' | 'red' | 'lightyellow'>(() => {
  if (props.status === DesktopStatusEnum.STARTED) return 'green'
  if (props.status === DesktopStatusEnum.FAILED) return 'red'
  if (props.status === DesktopStatusEnum.STOPPED) return 'gray'
  return 'lightyellow'
})

const hasHardware = computed(
  () => props.vcpu != null || props.ram != null || props.bootOrder || props.diskBus || props.vga
)
const hasSoftware = computed(
  () =>
    (props.viewers && props.viewers.length > 0) ||
    props.fullscreen != null ||
    (props.isos && props.isos.length > 0) ||
    (props.floppies && props.floppies.length > 0)
)
const hasReservables = computed(() => props.reservables && props.reservables.length > 0)
</script>

<template>
  <div class="flex flex-col gap-5 text-gray-warm-700">
    <!-- Identification — name, description, status, IP -->
    <section class="flex flex-col gap-3">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex flex-col gap-0.5">
          <p
            v-if="props.template"
            class="text-xs uppercase tracking-wide text-gray-warm-500 font-semibold"
          >
            {{ t(`components.domain-info-modal.${props.kind}.fields.template.title`) }}
          </p>
          <p v-if="props.template" class="text-sm font-semibold truncate">
            {{ props.template?.name }}
          </p>
        </div>
        <Badge
          v-if="props.status && props.kind === 'desktop'"
          :color="statusBadgeColor"
          :content="props.status"
          shape="square"
          size="sm"
          class="font-bold shrink-0"
        />
      </div>

      <p v-if="props.description" class="text-sm text-gray-warm-700">
        {{ props.description }}
      </p>

      <!-- ID rows (only when ctrl+alt+i toggled in parent) -->
      <div
        v-if="showId || props.ip"
        class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm"
      >
        <div v-if="showId" class="flex items-center gap-2 min-w-0">
          <span class="text-xs uppercase tracking-wide text-gray-warm-500 shrink-0">
            {{ t(`components.domain-info-modal.${props.kind}.fields.id`) }}
          </span>
          <code
            class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-0.5 truncate flex-1"
          >
            {{ props.domainId }}
          </code>
          <CopyIcon :value="props.domainId" size="sm" stroke-color="gray-warm-600" />
        </div>
        <div v-if="props.template && showId" class="flex items-center gap-2 min-w-0">
          <span class="text-xs uppercase tracking-wide text-gray-warm-500 shrink-0">
            {{ t(`components.domain-info-modal.${props.kind}.fields.template.id`) }}
          </span>
          <code
            class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-0.5 truncate flex-1"
          >
            {{ props.template?.id }}
          </code>
          <CopyIcon :value="props.template?.id || ''" size="sm" stroke-color="gray-warm-600" />
        </div>
        <div v-if="props.ip" class="flex items-center gap-2 min-w-0">
          <Icon name="signal-01" size="sm" stroke-color="gray-warm-600" class="shrink-0" />
          <span class="text-xs uppercase tracking-wide text-gray-warm-500 shrink-0">
            {{ t('components.domain-info-modal.fields.ip.title') }}
          </span>
          <code
            class="font-mono text-xs bg-gray-warm-50 border border-gray-warm-200 rounded px-2 py-0.5 truncate flex-1"
          >
            {{ props.ip }}
          </code>
          <CopyIcon :value="props.ip" size="sm" stroke-color="gray-warm-600" />
        </div>
      </div>
    </section>

    <!-- Hardware -->
    <section v-if="hasHardware" class="flex flex-col gap-2">
      <h4
        class="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-gray-warm-500"
      >
        <Icon name="cpu" size="sm" stroke-color="gray-warm-500" />
        {{ t('components.domain-info-modal.fields.hardware.title') }}
      </h4>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-sm pl-6">
        <div v-if="props.vcpu != null" class="flex items-center gap-2">
          <Icon name="cpu" size="sm" stroke-color="gray-warm-700" />
          <span class="font-semibold">{{
            t('components.domain-info-modal.fields.hardware.vcpu', { vcpu: props.vcpu })
          }}</span>
        </div>
        <div v-if="props.ram != null" class="flex items-center gap-2">
          <Icon name="memory" size="sm" stroke-color="gray-warm-700" />
          <span class="font-semibold">{{
            t('components.domain-info-modal.fields.hardware.ram', { ram: props.ram?.toFixed(2) })
          }}</span>
        </div>
        <div v-if="props.bootOrder" class="flex items-center gap-2">
          <Icon name="hdd" size="sm" stroke-color="gray-warm-700" />
          <span class="font-semibold truncate">{{ props.bootOrder.join(', ') }}</span>
        </div>
        <div v-if="props.diskBus" class="flex items-center gap-2">
          <Icon name="hdd-02" size="sm" stroke-color="gray-warm-700" />
          <span class="font-semibold truncate">{{ props.diskBus }}</span>
        </div>
        <div v-if="props.vga" class="flex items-center gap-2 sm:col-span-2">
          <Icon name="wires" size="sm" stroke-color="gray-warm-700" />
          <span class="font-semibold truncate">{{ props.vga.join(', ') }}</span>
        </div>
      </div>
    </section>

    <!-- Software / access — viewers, fullscreen, peripherals -->
    <section v-if="hasSoftware" class="flex flex-col gap-2">
      <h4
        class="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-gray-warm-500"
      >
        <Icon name="monitor" size="sm" stroke-color="gray-warm-500" />
        {{ t('components.domain-info-modal.fields.viewers.title') }}
      </h4>
      <div class="flex flex-col gap-1.5 pl-6 text-sm">
        <div v-if="props.viewers && props.viewers.length" class="flex items-start gap-2">
          <Icon name="monitor" size="sm" stroke-color="gray-warm-700" class="mt-0.5" />
          <span class="font-semibold">
            {{
              props.viewers
                .map((viewer) => t(`viewers.${viewer.toLowerCase().replace('_', '-')}`))
                .join(', ')
            }}
          </span>
        </div>
        <div v-if="props.fullscreen != null" class="flex items-center gap-2 text-gray-warm-600">
          <Icon
            :name="props.fullscreen ? 'check-circle' : 'minus-circle'"
            size="sm"
            :stroke-color="props.fullscreen ? 'success-600' : 'gray-warm-500'"
          />
          <span>{{
            props.fullscreen
              ? t('components.domain-info-modal.fields.viewers.fullscreen-enabled')
              : t('components.domain-info-modal.fields.viewers.fullscreen-disabled')
          }}</span>
        </div>
        <template
          v-if="(props.isos && props.isos.length) || (props.floppies && props.floppies.length)"
        >
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <div v-for="iso in props.isos" :key="iso" class="flex items-center gap-2">
              <Icon name="disc-02" size="sm" stroke-color="gray-warm-700" />
              <span class="font-semibold truncate">{{ iso }}</span>
            </div>
            <div v-for="floppy in props.floppies" :key="floppy" class="flex items-center gap-2">
              <Icon name="save-01" size="sm" stroke-color="gray-warm-700" />
              <span class="font-semibold truncate">{{ floppy }}</span>
            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- Reservables -->
    <section v-if="hasReservables" class="flex flex-col gap-2">
      <h4
        class="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-gray-warm-500"
      >
        <Icon name="gpu" size="sm" stroke-color="gray-warm-500" />
        {{ t('components.domain-info-modal.fields.reservables.title') }}
      </h4>
      <div class="flex items-center gap-2 pl-6 text-sm">
        <Icon name="gpu" size="sm" stroke-color="gray-warm-700" />
        <span class="font-semibold">{{ props.reservables?.join(', ') }}</span>
      </div>
    </section>
  </div>
</template>
