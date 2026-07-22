<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { Modal } from '@/components/modal'
import type { DesktopTemplate } from '@/gen/oas/apiv4'
import DomainInfoContent from './DomainInfoContent.vue'

const { t } = useI18n()

export interface DomainInfoItem {
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
}

export interface Props {
  open?: boolean
  domainId?: string
  name?: string
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
  items?: DomainInfoItem[]
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  domainId: '-',
  name: '',
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
  items: undefined
})

const emit = defineEmits<{
  close: []
}>()

const resolvedItems = computed<DomainInfoItem[]>(() => {
  if (props.items && props.items.length > 0) {
    return props.items
  }
  return [
    {
      domainId: props.domainId,
      name: props.name,
      description: props.description,
      status: props.status,
      ip: props.ip,
      vcpu: props.vcpu,
      ram: props.ram,
      bootOrder: props.bootOrder,
      diskBus: props.diskBus,
      vga: props.vga,
      viewers: props.viewers,
      fullscreen: props.fullscreen,
      isos: props.isos,
      floppies: props.floppies,
      reservables: props.reservables,
      kind: props.kind,
      template: props.template
    }
  ]
})

// show id column if user presses ctrl+alt+i
const showId = ref(false)
window.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'i') {
    showId.value = !showId.value
  }
})

const closeModal = () => {
  showId.value = false
  emit('close')
}
</script>

<template>
  <Modal
    :title="t('components.domain-info-modal.title')"
    :open="props.open"
    class="max-w-140 pt-6"
    @close="closeModal()"
  >
    <div class="flex flex-col gap-6">
      <div
        v-for="(item, index) in resolvedItems"
        :key="item.domainId ?? index"
        class="bg-base-white p-5 rounded-lg border border-gray-warm-300"
      >
        <h3 class="text-gray-warm-600 text-sm mb-4">
          <span>{{
            `${t(`components.domain-info-modal.${props.kind}.description-prefix`)}: `
          }}</span>
          <span class="font-semibold">{{ item.name }}</span>
        </h3>
        <DomainInfoContent v-bind="item" :show-id="showId" />
      </div>
    </div>
  </Modal>
</template>
