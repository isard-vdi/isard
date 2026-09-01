<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import {
  getStorageOptions,
  getStorageQueryKey,
  getStorageTaskQueryKey,
  increaseStorageSizeMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  DesktopStatusEnum,
  type ApiSchemasDomainsDesktopsUserDesktop as UserDesktop
} from '@/gen/oas/apiv4'

import { describeApiError } from '@/lib/api-errors'
import { isNotUser } from '@/lib/auth'
import { useAuthStore } from '@/stores/auth'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import Badge from '@/components/badge/Badge.vue'
import { CopyIcon, Icon } from '@/components/icon'
import InputField from '@/components/input-field/InputField.vue'

interface Props {
  desktop: UserDesktop
  storageId: string
  showId?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showId: false
})

const emit = defineEmits<{
  error: [message: string]
  success: []
}>()

const i18n = useI18n()
const { t } = i18n
const authStore = useAuthStore()
const queryClient = useQueryClient()

// Storage GET response is typed `unknown` by the codegen because the
// apiv4 service returns the raw row dict.
interface StorageDetail {
  id: string
  status?: string
  user_id?: string
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

const desktopIsStopped = computed(() => props.desktop.status === DesktopStatusEnum.STOPPED)

// Same rule the storage option declares in the advanced options registry.
const canSeeIncrease = computed(() => isNotUser(userRole.value))
const increaseDisabled = computed(
  () => !desktopIsStopped.value || storage.value?.status !== 'ready'
)

const increaseDisabledReason = computed(() => {
  if (!increaseDisabled.value) return ''
  return !desktopIsStopped.value
    ? t('components.desktops.desktop-storage-modal.actions.increase-needs-stopped')
    : t('components.desktops.desktop-storage-modal.actions.increase-needs-ready')
})

const incrementFieldId = computed(() => `storage-increment-${props.storageId}`)
const increment = ref<number>(10)

const virtualSize = computed(() => storage.value?.['qemu-img-info']?.['virtual-size'])
const virtualSizeGb = computed(() => (virtualSize.value ?? 0) / 1024 ** 3)

const MAX_VIRTUAL_SIZE_GB = 2048

// Without `qemu-img-info` the current size is unknown, so the ceiling
// applies to the increment on its own.
const availableGb = computed(() =>
  Math.max(0, Math.floor(MAX_VIRTUAL_SIZE_GB - virtualSizeGb.value))
)

const badInput = ref(false)
const onIncrementInput = (event: Event) => {
  badInput.value = (event.target as HTMLInputElement).validity?.badInput ?? false
}

const incrementError = computed(() => {
  const key = (name: string) => `components.desktops.desktop-storage-modal.increase.errors.${name}`
  if (badInput.value) return t(key('not-a-number'))
  if (!Number.isFinite(increment.value)) return t(key('required'))
  if (!Number.isInteger(increment.value)) return t(key('not-an-integer'))
  if (increment.value <= 0) return t(key('too-small'))
  if (increment.value > availableGb.value) {
    return t(key('too-large'), { max: MAX_VIRTUAL_SIZE_GB, available: availableGb.value })
  }
  return ''
})

// The endpoint takes the increment in GB and qemu resizes in GiB.
const increasedVirtualSize = computed(() => {
  if (!virtualSize.value || incrementError.value) return undefined
  return virtualSize.value + increment.value * 1024 ** 3
})

const { mutate: increaseSize, isPending: increaseIsPending } = useMutation({
  ...increaseStorageSizeMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({
      queryKey: getStorageQueryKey({
        path: { storage_id: props.storageId }
      })
    })
    queryClient.invalidateQueries({
      queryKey: getStorageTaskQueryKey({
        path: { storage_id: props.storageId }
      })
    })
    emit('success')
  },
  onError: (error) => {
    emit('error', describeApiError(error, i18n, 'increase-storage'))
  }
})

const submitIncrease = () => {
  if (incrementError.value || increaseDisabled.value || increaseIsPending.value) return
  increaseSize({
    path: {
      storage_id: props.storageId,
      // The apiv4 endpoint forces priority="low" for non-admins and
      // accepts "low"/"default"/"high" for admins. v1 always submits
      // "low" to match v3's @is_not_user behaviour.
      priority: 'low',
      increment: increment.value
    }
  })
}

const desktopStatusLabel = computed(() => {
  const key = `components.desktops.desktop-card.status.${props.desktop.status?.toLowerCase()}.text`
  return i18n.te(key) ? t(key) : t('components.desktops.desktop-card.status.unknown.text')
})

const desktopStatusColor = computed<'green' | 'red' | 'gray' | 'lightyellow'>(() => {
  switch (props.desktop.status) {
    case DesktopStatusEnum.STARTED:
      return 'green'
    case DesktopStatusEnum.FAILED:
      return 'red'
    case DesktopStatusEnum.STOPPED:
      return 'gray'
    default:
      return 'lightyellow'
  }
})

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
  <section class="flex flex-col gap-5" :data-testid="`desktop-storage-item-${props.storageId}`">
    <div v-if="storageIsPending" class="flex flex-col gap-2">
      <Skeleton class="h-5 w-40" />
      <Skeleton class="h-4 w-32" />
    </div>
    <template v-else-if="storage">
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-4 my-2">
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] font-bold uppercase tracking-wide text-gray-warm-500">
              {{ t('components.desktops.desktop-storage-modal.desktop-status') }}
            </span>
            <Badge
              :color="desktopStatusColor"
              :content="desktopStatusLabel"
              shape="square"
              size="sm"
            />
          </div>

          <div class="flex items-center gap-1.5">
            <span class="text-[10px] font-bold uppercase tracking-wide text-gray-warm-500">
              {{ t('components.desktops.desktop-storage-modal.disk-status') }}
            </span>
            <Badge :color="statusBadgeColor" :content="statusLabel" shape="square" size="sm" />
          </div>

          <div v-if="props.showId" class="flex min-w-0 items-center gap-1.5">
            <span class="shrink-0 text-[10px] font-bold uppercase tracking-wide text-brand-700">
              {{ t('components.desktops.desktop-storage-modal.disk-id') }}
            </span>
            <div
              class="flex min-w-0 items-center gap-2.5 rounded-lg border border-gray-warm-200 bg-gray-warm-25 px-2 py-1 shadow-xs"
            >
              <span class="truncate font-mono text-xs text-gray-warm-700">{{ storage.id }}</span>
              <CopyIcon :value="storage.id" size="md" stroke-color="gray-warm-600" />
            </div>
          </div>
        </div>

        <div class="border border-gray-warm-200 rounded-lg py-2 px-4">
          <dl class="grid grid-cols-3">
            <div class="pr-5">
              <dt class="text-xs font-semibold text-gray-warm-600">
                {{ t('components.desktops.desktop-storage-modal.format') }}
              </dt>
              <dd class="text-md font-bold uppercase text-brand-700">
                {{ storage.type ?? '—' }}
              </dd>
            </div>

            <div class="border-l border-gray-warm-200 px-5 text-center">
              <dt class="text-xs font-semibold text-gray-warm-600">
                {{ t('components.desktops.desktop-storage-modal.virtual-size') }}
              </dt>
              <dd class="text-md font-bold text-brand-700">
                {{ formatBytes(storage['qemu-img-info']?.['virtual-size']) }}
              </dd>
            </div>

            <div class="border-l border-gray-warm-200 pl-5 text-right">
              <dt class="text-xs font-semibold text-gray-warm-600">
                {{ t('components.desktops.desktop-storage-modal.actual-size') }}
              </dt>
              <dd class="text-md font-bold text-brand-700">
                {{ formatBytes(storage['qemu-img-info']?.['actual-size']) }}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <form
        v-if="canSeeIncrease"
        class="flex flex-col gap-4 bg-gray-warm-100 p-3 rounded-md border border-gray-warm-200 shadow-xs"
        @submit.prevent="submitIncrease"
      >
        <div class="flex gap-2 flex-col">
          <div class="flex items-center gap-1.5">
            <label class="text-sm font-semibold text-gray-warm-700" :for="incrementFieldId">
              {{ t('components.desktops.desktop-storage-modal.increase.field-label') }}
            </label>
            <Tooltip>
              <TooltipTrigger as-child>
                <span
                  class="inline-flex cursor-help text-gray-warm-500"
                  :aria-label="t('components.desktops.desktop-storage-modal.increase.help-title')"
                >
                  <Icon name="info-circle" size="sm" stroke-color="currentColor" />
                </span>
              </TooltipTrigger>
              <TooltipContent
                :title="t('components.desktops.desktop-storage-modal.increase.help-title')"
                :subtitle="t('components.desktops.desktop-storage-modal.increase.help-subtitle')"
              />
            </Tooltip>
          </div>
          <div class="flex items-center gap-3">
            <InputField
              :id="incrementFieldId"
              v-model="increment"
              type="number"
              class="w-32 shrink-0"
              :min="1"
              :max="availableGb"
              :step="1"
              :destructive="!!incrementError"
              :disabled="increaseIsPending"
              :aria-describedby="incrementError ? `${incrementFieldId}-error` : undefined"
              @input="onIncrementInput"
            />
            <p
              v-if="increasedVirtualSize"
              class="flex min-w-0 items-center gap-3.5 text-sm text-gray-warm-600"
              :aria-label="
                t('components.desktops.desktop-storage-modal.increase.preview', {
                  size: formatBytes(increasedVirtualSize)
                })
              "
            >
              <span aria-hidden="true">{{ formatBytes(virtualSize) }}</span>
              <Icon
                name="arrow-narrow-right"
                size="sm"
                stroke-color="currentColor"
                aria-hidden="true"
              />
              <span class="font-semibold text-gray-warm-900" aria-hidden="true">
                {{ formatBytes(increasedVirtualSize) }}
              </span>
            </p>
          </div>
          <p v-if="incrementError" :id="`${incrementFieldId}-error`" class="text-xs text-error-700">
            {{ incrementError }}
          </p>
        </div>
        <div class="flex items-center w-full">
          <Tooltip>
            <TooltipTrigger as-child>
              <!-- Wrapper: a disabled button emits no pointer events -->
              <span class="inline-flex w-full">
                <Button
                  hierarchy="secondary-color"
                  type="button"
                  class="w-full"
                  size="sm"
                  icon="plus"
                  :disabled="increaseDisabled || increaseIsPending || !!incrementError"
                  @click="submitIncrease"
                >
                  {{ t('components.desktops.desktop-storage-modal.actions.increase') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent v-if="increaseDisabledReason" :title="increaseDisabledReason" />
          </Tooltip>
        </div>
      </form>

      <p v-else class="text-xs text-gray-warm-500">
        {{ t('components.desktops.desktop-storage-modal.actions.no-actions') }}
      </p>
    </template>
    <div v-else class="text-sm text-error-700">
      {{ t('components.desktops.desktop-storage-modal.load-error') }}
    </div>
  </section>
</template>
