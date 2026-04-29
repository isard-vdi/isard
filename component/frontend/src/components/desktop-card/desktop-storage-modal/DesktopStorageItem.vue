<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { getStorageOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum, type UserDesktop } from '@/gen/oas/apiv4'

import { useAuthStore } from '@/stores/auth'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import Badge from '@/components/badge/Badge.vue'

import CancelStorageOperationModal from './CancelStorageOperationModal.vue'
import IncreaseStorageSizeModal from './IncreaseStorageSizeModal.vue'

interface Props {
  desktop: UserDesktop
  storageId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  error: [message: string]
}>()

const { t } = useI18n()
const authStore = useAuthStore()

// Storage GET response is typed `unknown` by the codegen because the
// apiv4 service returns the raw row dict. Narrow it to the fields the
// modal actually reads — keep this minimal so a backend addition
// doesn't force a frontend type churn.
interface StorageDetail {
  id: string
  status?: string
  user_id?: string
  task?: string | null
  parent?: string | null
  type?: string
  ['qemu-img-info']?: {
    'virtual-size'?: number
    'actual-size'?: number
  }
}

const { data: rawStorage, isPending: storageIsPending } = useQuery(
  getStorageOptions({
    path: { storage_id: props.storageId }
  })
)

const storage = computed<StorageDetail | undefined>(() =>
  rawStorage.value ? (rawStorage.value as StorageDetail) : undefined
)

const userRole = computed(() => authStore.user?.role_id ?? 'user')
const userId = computed(() => authStore.user?.id ?? '')

const desktopIsStopped = computed(() => props.desktop.status === DesktopStatusEnum.STOPPED)

// Show Increase iff the user is `advanced`/`manager`/`admin` (matches v3
// `@is_not_user`) and the desktop is stopped. Disable visually when the
// underlying storage row is not in `ready` state.
const canSeeIncrease = computed(() => userRole.value !== 'user')
const increaseDisabled = computed(
  () => !desktopIsStopped.value || storage.value?.status !== 'ready'
)

// Show Cancel iff the storage has a current task. Server enforces
// ownership (owner/admin always, manager when in same category) — we
// hide for plain users on someone else's task to avoid a guaranteed 403.
const canSeeCancel = computed(() => {
  if (!storage.value?.task) return false
  if (userRole.value === 'admin' || userRole.value === 'manager') return true
  return storage.value.user_id === userId.value
})
const cancelDisabled = computed(() => !storage.value?.task)

const showCancelModal = ref(false)
const showIncreaseModal = ref(false)

const statusBadgeColor = computed<'green' | 'red' | 'gray' | 'lightyellow'>(() => {
  switch (storage.value?.status) {
    case 'ready':
      return 'green'
    case 'maintenance':
    case 'downloading':
      return 'lightyellow'
    case 'deleted':
    case 'orphan':
    case 'broken_chain':
      return 'red'
    default:
      return 'gray'
  }
})

// Keep this Set in sync with the keys under
// `components.desktops.desktop-storage-modal.status` in the locale
// files. Anything outside this list renders the raw value verbatim
// rather than the literal `status.<value>` key path.
const knownStatuses = new Set([
  'ready',
  'maintenance',
  'deleted',
  'orphan',
  'broken_chain',
  'non_existing',
  'downloading',
  'unknown'
])

const statusLabel = computed(() => {
  const status = storage.value?.status
  if (status && knownStatuses.has(status)) {
    return t(`components.desktops.desktop-storage-modal.status.${status}`)
  }
  return status ?? '—'
})

const formatBytes = (n?: number): string => {
  if (!n || !Number.isFinite(n)) return '—'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}
</script>

<template>
  <div
    class="flex flex-col gap-3 rounded-md border border-gray-warm-200 bg-base-white p-4"
    :data-testid="`desktop-storage-item-${props.storageId}`"
  >
    <div v-if="storageIsPending" class="flex flex-col gap-2">
      <Skeleton class="h-5 w-40" />
      <Skeleton class="h-4 w-32" />
    </div>
    <template v-else-if="storage">
      <div class="flex items-start justify-between gap-3">
        <div class="flex flex-col gap-1 min-w-0">
          <div class="text-xs text-gray-warm-500 font-mono truncate" :title="storage.id">
            {{ storage.id }}
          </div>
          <div class="flex items-center gap-2">
            <Badge :color="statusBadgeColor">{{ statusLabel }}</Badge>
            <span v-if="storage.type" class="text-xs text-gray-warm-600 uppercase">{{
              storage.type
            }}</span>
          </div>
        </div>
        <div class="flex flex-col items-end shrink-0 text-xs text-gray-warm-600">
          <span class="font-semibold">{{
            t('components.desktops.desktop-storage-modal.virtual-size')
          }}</span>
          <span>{{ formatBytes(storage['qemu-img-info']?.['virtual-size']) }}</span>
          <span class="font-semibold mt-1">{{
            t('components.desktops.desktop-storage-modal.actual-size')
          }}</span>
          <span>{{ formatBytes(storage['qemu-img-info']?.['actual-size']) }}</span>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-warm-100">
        <Tooltip v-if="canSeeCancel">
          <TooltipTrigger as-child>
            <Button
              hierarchy="destructive"
              size="sm"
              icon="stop"
              :disabled="cancelDisabled"
              @click="showCancelModal = true"
            >
              {{ t('components.desktops.desktop-storage-modal.actions.cancel') }}
            </Button>
          </TooltipTrigger>
          <TooltipContent
            :title="t('components.desktops.desktop-storage-modal.actions.cancel-tooltip')"
          />
        </Tooltip>

        <Tooltip v-if="canSeeIncrease">
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-color"
              size="sm"
              icon="plus"
              :disabled="increaseDisabled"
              @click="showIncreaseModal = true"
            >
              {{ t('components.desktops.desktop-storage-modal.actions.increase') }}
            </Button>
          </TooltipTrigger>
          <TooltipContent
            :title="
              !desktopIsStopped
                ? t('components.desktops.desktop-storage-modal.actions.increase-needs-stopped')
                : storage.status !== 'ready'
                  ? t('components.desktops.desktop-storage-modal.actions.increase-needs-ready')
                  : t('components.desktops.desktop-storage-modal.actions.increase-tooltip')
            "
          />
        </Tooltip>

        <span v-if="!canSeeCancel && !canSeeIncrease" class="text-xs text-gray-warm-500">
          {{ t('components.desktops.desktop-storage-modal.actions.no-actions') }}
        </span>
      </div>
    </template>
    <div v-else class="text-sm text-error-700">
      {{ t('components.desktops.desktop-storage-modal.load-error') }}
    </div>

    <CancelStorageOperationModal
      :open="showCancelModal"
      :storage-id="props.storageId"
      :desktop-name="props.desktop.name"
      @close="showCancelModal = false"
      @error="(msg) => emit('error', msg)"
    />
    <IncreaseStorageSizeModal
      :open="showIncreaseModal"
      :storage-id="props.storageId"
      @close="showIncreaseModal = false"
      @error="(msg) => emit('error', msg)"
    />
  </div>
</template>
