<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'

interface Props {
  vcpu?: number
  memory?: number
  diskBus?: string
  diskSize?: number
  videos?: string[]
  bootOrder?: string[]
  isos?: string[]
  floppies?: string[]
  vgpus?: string[] | null
  loading?: boolean
  interfaces?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  vcpu: undefined,
  memory: undefined,
  bootOrder: undefined,
  diskBus: undefined,
  diskSize: undefined,
  videos: undefined,
  isos: undefined,
  floppies: undefined,
  vgpus: undefined,
  interfaces: undefined
})

const { t } = useI18n()

const hasSystemInfo = computed(() => {
  return (
    props.vcpu || props.memory || props.diskSize || props.bootOrder || props.diskBus || props.videos
  )
})

const hasPeripherals = computed(() => {
  return (props.isos && props.isos.length > 0) || (props.floppies && props.floppies.length > 0)
})

const hasReservables = computed(() => {
  return props.vgpus && props.vgpus.length > 0
})
</script>
<template>
  <div class="bg-gray-warm-50 p-4 rounded-md border border-gray-warm-200 grid grid-cols-3 gap-6">
    <!-- System -->
    <div v-if="hasSystemInfo" class="flex flex-col col-span-2 gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-hardware-summary.system.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2">
          <Icon name="cpu" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold"
            >{{ props.vcpu }} {{ t('components.domain.hardware.vcpus.label') }}</span
          >
        </div>
        <div class="flex items-center gap-2">
          <Icon name="memory" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold"
            >{{ props.memory?.toFixed(2) }} {{ t('components.domain.hardware.memory.label') }}</span
          >
        </div>
        <div v-if="props.diskSize" class="flex items-center gap-2">
          <Icon name="hdd" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold"
            >{{ props.diskSize }} {{ t('components.domain.hardware.disk-size.label') }}</span
          >
        </div>
        <div v-if="props.bootOrder" class="flex items-center gap-2">
          <Icon name="hdd" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.bootOrder.join(', ') }}</span>
        </div>
        <div v-if="props.diskBus" class="flex items-center gap-2">
          <Icon name="hdd-02" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.diskBus }}</span>
        </div>
        <div v-if="props.videos" class="flex items-center gap-2">
          <Icon name="wires" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.videos.join(', ') }}</span>
        </div>
      </div>
    </div>

    <!-- Networks -->
    <div v-if="props.interfaces && props.interfaces.length > 0" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-hardware-summary.networks.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <Icon name="modem-02" size="sm" stroke-color="gray-warm-700" />
        <div v-for="network in props.interfaces" :key="network" class="flex items-center gap-2">
          <span class="text-sm font-semibold">{{ network }}</span>
        </div>
      </div>
    </div>

    <!-- Peripherals/ISOs -->
    <div v-if="hasPeripherals" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-hardware-summary.peripherals.title') }}
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
    <div v-if="hasReservables" class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-hardware-summary.reservables.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div v-if="props.vgpus" class="flex items-center gap-2">
        <Icon name="gpu" size="md" stroke-color="gray-warm-700" />
        <span class="text-sm font-semibold">{{ props.vgpus.join(', ') }}</span>
      </div>
    </div>
  </div>
</template>
