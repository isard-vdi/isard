<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal } from '@/components/modal'
import type { DesktopTemplate } from '@/gen/oas/apiv4'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import Badge from '@/components/badge/Badge.vue'
import DomainInfoContent from './DomainInfoContent.vue'
import { desktopStatusLabel } from '@/lib/desktops'
import { Icon } from '@/components/icon'

import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

const i18n = useI18n()
const { t } = i18n

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
  credentials?: { username?: string | null; password?: string | null } | null
  kind: 'desktop' | 'template'
  template?: DesktopTemplate | null
  desktopKind?: 'persistent' | 'nonpersistent' | 'deployment' | null
}

export interface Props {
  open?: boolean
  isLoading?: boolean
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
  credentials?: { username?: string | null; password?: string | null } | null
  kind: 'desktop' | 'template'
  template?: DesktopTemplate | null
  desktopKind?: 'persistent' | 'nonpersistent' | 'deployment' | null
  items?: DomainInfoItem[]
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  isLoading: false,
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
  credentials: undefined,
  desktopKind: undefined,
  items: undefined
})

const emit = defineEmits<{
  close: []
}>()

const resolvedItems = computed<DomainInfoItem[]>(() => {
  // `items` is only passed in list mode (e.g. deployment desktops); an empty
  // array there means "no results", not "fall back to single-domain props".
  if (props.items !== undefined) {
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
      credentials: props.credentials,
      kind: props.kind,
      template: props.template,
      desktopKind: props.desktopKind
    }
  ]
})

const emptyStateKindLabel = computed(() =>
  t(`domains.${props.kind === 'template' ? 'templates' : 'desktops'}`, 0)
)

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

const statusLabel = (status?: string) => desktopStatusLabel(status, i18n)

const statusBadgeColor = (status?: string): 'green' | 'gray' | 'red' | 'lightyellow' => {
  if (status === DesktopStatusEnum.STARTED) return 'green'
  if (status === DesktopStatusEnum.FAILED) return 'red'
  if (status === DesktopStatusEnum.STOPPED) return 'gray'
  return 'lightyellow'
}

const resolveKind = (
  item: DomainInfoItem
): 'persistent' | 'nonpersistent' | 'deployment' | undefined => {
  if (item.kind !== 'desktop' || item.desktopKind == null) return undefined
  return item.desktopKind
}

const nameBadgeClass = (item: DomainInfoItem): string => {
  const kind = resolveKind(item)
  if (kind === 'persistent') return 'bg-secondary-3-300 text-secondary-3-600'
  if (kind === 'nonpersistent') return 'bg-secondary-1-300 text-secondary-1-600'
  if (kind === 'deployment') return 'bg-secondary-2-300 text-secondary-2-600'
  return 'bg-brand-700 text-base-white'
}

const cardBorderClass = (item: DomainInfoItem): string => {
  const kind = resolveKind(item)
  if (kind === 'persistent') return 'border-l-6 border-l-secondary-3-500'
  if (kind === 'nonpersistent') return 'border-l-6 border-l-secondary-1-500'
  if (kind === 'deployment') return 'border-l-6 border-l-secondary-2-500'
  return 'border-l-6 border-l-brand-700'
}

const kindSrLabel = (item: DomainInfoItem): string => {
  const kind = resolveKind(item)
  if (!kind) return ''
  return t(`components.domain-info-modal.kind.${kind}`)
}
</script>

<template>
  <Modal
    :title="t('components.domain-info-modal.title')"
    :open="props.open"
    size="2xl"
    @close="closeModal()"
  >
    <div class="flex flex-col gap-6">
      <div
        v-if="isLoading"
        class="bg-base-white p-3 rounded-lg border border-gray-warm-300"
        role="status"
        aria-busy="true"
      >
        <span class="sr-only">{{ t('components.domain-info-modal.loading') }}</span>
        <div class="flex items-center justify-between gap-3 pb-2" aria-hidden="true">
          <Skeleton class="h-7 w-40" />
          <Skeleton class="h-5 w-16 shrink-0" />
        </div>
        <Separator class="my-1.5" />
        <div class="flex flex-col gap-3 pt-1" aria-hidden="true">
          <Skeleton class="h-4 w-1/2" />
          <Skeleton class="h-4 w-1/3" />
          <div class="flex gap-1.5">
            <Skeleton class="h-6 w-16" />
            <Skeleton class="h-6 w-20" />
            <Skeleton class="h-6 w-14" />
          </div>
          <div class="flex gap-1.5">
            <Skeleton class="h-6 w-20" />
            <Skeleton class="h-6 w-16" />
          </div>
        </div>
      </div>
      <Empty
        v-else-if="resolvedItems.length === 0"
        class="p-6 bg-base-white border border-gray-warm-300"
      >
        <EmptyHeader class="gap-1.5">
          <EmptyMedia variant="icon">
            <Icon name="monitor" />
          </EmptyMedia>
          <EmptyTitle class="text-sm font-medium">
            {{ t('components.empty.title', { kind: emptyStateKindLabel }) }}
          </EmptyTitle>
        </EmptyHeader>
      </Empty>
      <div
        v-for="(item, index) in resolvedItems"
        v-else
        :key="item.domainId ?? index"
        class="bg-base-white py-5 px-4 rounded-lg border border-gray-warm-300"
        :class="cardBorderClass(item)"
      >
        <div class="flex items-center justify-between gap-3 pb-2">
          <h3
            class="flex items-center gap-1.5 px-1.5 rounded-xs font-semibold text-md min-w-0"
            :class="nameBadgeClass(item)"
          >
            <span v-if="kindSrLabel(item)" class="sr-only">{{ kindSrLabel(item) }}: </span>
            <span class="min-w-0 break-words">{{ item.name }}</span>
          </h3>
          <Badge
            v-if="item.status && item.kind === 'desktop'"
            :color="statusBadgeColor(item.status)"
            :content="statusLabel(item.status)"
            shape="square"
            size="sm"
            class="font-bold shrink-0"
          />
        </div>
        <Separator class="my-1.5" />
        <DomainInfoContent v-bind="item" :show-id="showId" />
      </div>
    </div>
  </Modal>
</template>
