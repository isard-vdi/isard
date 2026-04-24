<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { CopyIcon, Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'
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
</script>

<template>
  <div class="flex flex-col gap-5 text-gray-warm-700">
    <!-- Template Name -->
    <div v-if="props.template" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t(`components.domain-info-modal.${props.kind}.fields.template.title`) }}
        </div>
        <Separator class="flex-1" />
      </div>
      <p class="text-sm font-semibold">{{ props.template?.name }}</p>
    </div>

    <!-- Template ID -->
    <div v-if="props.template && showId" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t(`components.domain-info-modal.${props.kind}.fields.template.id`) }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-2.5">
        <span class="text-sm font-semibold">{{ props.template?.id }}</span>
        <CopyIcon :value="props.template?.id || ''" size="md" stroke-color="gray-warm-600" />
      </div>
    </div>

    <!-- Description -->
    <div v-if="props.description" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.description.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <p class="text-sm font-semibold">{{ props.description }}</p>
    </div>

    <!-- Desktop ID -->
    <div v-if="showId" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t(`components.domain-info-modal.${props.kind}.fields.id`) }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-2.5">
        <span class="text-sm font-semibold">{{ props.domainId }}</span>
        <CopyIcon :value="props.domainId" size="md" stroke-color="gray-warm-600" />
      </div>
    </div>

    <!-- Status Section -->
    <div v-if="props.status && props.kind === 'desktop'" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.status.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-2">
        <Badge
          :color="props.status === DesktopStatusEnum.STARTED ? 'green' : 'gray'"
          :content="props.status"
          shape="square"
          size="sm"
          class="font-bold"
        />
      </div>
    </div>

    <!-- IP Address -->
    <div v-if="props.ip" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.ip.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-2.5">
        <span class="text-sm font-semibold">{{ props.ip }}</span>
        <CopyIcon :value="props.ip" size="md" stroke-color="gray-warm-600" />
      </div>
    </div>

    <!-- Hardware -->
    <div v-if="props.vcpu || props.ram" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.hardware.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2">
          <Icon name="cpu" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            t('components.domain-info-modal.fields.hardware.vcpu', { vcpu: props.vcpu })
          }}</span>
        </div>
        <div class="flex items-center gap-2">
          <Icon name="memory" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            t('components.domain-info-modal.fields.hardware.ram', { ram: props.ram?.toFixed(2) })
          }}</span>
        </div>
      </div>
    </div>

    <!-- System -->
    <div v-if="props.bootOrder || props.diskBus || props.vga" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.system.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8 flex-wrap">
        <div v-if="props.bootOrder" class="flex items-center gap-2">
          <Icon name="hdd" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.bootOrder.join(', ') }}</span>
        </div>
        <div v-if="props.diskBus" class="flex items-center gap-2">
          <Icon name="hdd-02" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.diskBus }}</span>
        </div>
        <div v-if="props.vga" class="flex items-center gap-2">
          <Icon name="wires" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.vga.join(', ') }}</span>
        </div>
      </div>
    </div>

    <!-- Viewers -->
    <div v-if="props.viewers" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.viewers.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <Icon name="monitor" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            props.viewers
              .map((viewer) => t(`viewers.${viewer.toLowerCase().replace('_', '-')}`))
              .join(', ')
          }}</span>
        </div>
        <div class="flex items-center gap-2">
          <Icon name="monitor" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            props.fullscreen
              ? t('components.domain-info-modal.fields.viewers.fullscreen-enabled')
              : t('components.domain-info-modal.fields.viewers.fullscreen-disabled')
          }}</span>
        </div>
      </div>
    </div>

    <!-- Peripherals/ISOs -->
    <div v-if="props.isos || props.floppies" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.peripherals.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <div v-for="iso in props.isos" :key="iso" class="flex items-center gap-2">
          <Icon name="disc-02" size="sm" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ iso }}</span>
        </div>
        <div v-for="floppy in props.floppies" :key="floppy" class="flex items-center gap-2">
          <Icon name="save-01" size="sm" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ floppy }}</span>
        </div>
      </div>
    </div>

    <!-- Reservables -->
    <div v-if="props.reservables" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-info-modal.fields.reservables.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-2">
        <Icon name="gpu" size="md" stroke-color="gray-warm-700" />
        <span class="text-sm font-semibold">{{ props.reservables.join(', ') }}</span>
      </div>
    </div>
  </div>
</template>
