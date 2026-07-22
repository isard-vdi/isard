<script setup lang="ts">
import { computed, reactive, watchEffect } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { Modal } from '@/components/modal'
import { Spinner } from '@/components/ui/spinner'
import { Progress } from '@/components/ui/progress'
import { MetricItem } from '@/components/metric-item'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'

import { getUserQuotas, type UserQuota, type UserQuotaUsed } from '@/gen/oas/apiv4'

const open = defineModel<boolean>('open')

const { isPending: loading, data: rawData } = useQuery({
  queryKey: ['userQuotas'],
  queryFn: () => getUserQuotas(),
  enabled: open
})

const data = computed(() => rawData.value?.data)

function handleClose() {
  open.value = false
}

const METRICS = [
  { key: 'desktops', icon: 'monitor-02' },
  { key: 'volatile', icon: 'zap' },
  { key: 'templates', icon: 'colors' },
  { key: 'isos', label: 'media', icon: 'disc-02' },
  { key: 'deployments_total', icon: 'layout-alt-04' },
  { key: 'deployment_desktops', icon: 'layers-three-01' },
  { key: 'deployment_users', icon: 'users-01' },
  { key: 'started_deployment_desktops', icon: 'play-circle' },
  { key: 'running', icon: 'play' },
  { key: 'memory', icon: 'memory' },
  { key: 'vcpus', icon: 'cpu-chip-01' }
] as const

const metrics = reactive<
  { name: string; icon: string; info: { current: number; total: number } }[]
>([])

watchEffect(() => {
  if (!data.value) return

  metrics.length = 0
  for (const raw of METRICS) {
    const name = raw.key
    const label = 'label' in raw ? raw.label : raw.key
    const current = data.value.used[name as keyof UserQuotaUsed]
    const total = data.value.quota
      ? (data.value.quota[name as keyof UserQuota] ?? Infinity)
      : Infinity

    metrics.push({
      name: label,
      icon: raw.icon,
      info: {
        current,
        total
      }
    })
  }
})

const total = computed(() => {
  if (!data.value) return
  const current = data.value.used['total_size' as keyof UserQuotaUsed]
  const total = data.value.quota
    ? (data.value.quota['total_size' as keyof UserQuota] ?? Infinity)
    : Infinity
  if (typeof current === 'undefined' || typeof total === 'undefined') return undefined
  return { current, total }
})
const totalPercent = computed(() => {
  const value = total.value
  if (typeof value === 'undefined') return
  if (!value.current) return 0
  if (value.total === Infinity) return 0
  return Math.min(100, (value.current * 100) / value.total)
})
const totalColor = computed(() =>
  typeof totalPercent.value == 'undefined'
    ? undefined
    : totalPercent.value >= 50
      ? totalPercent.value >= 100
        ? 'text-error-400'
        : 'text-warning-400'
      : 'text-success-400'
)
</script>

<template>
  <Modal
    :open
    :title="$t('components.profile.quota-modal.title')"
    :description="$t('components.profile.quota-modal.description')"
    size="5xl"
    @close="handleClose"
  >
    <div v-if="loading">
      <Spinner color="green" class="m-auto mb-10 mt-10" />
    </div>
    <div v-else class="flex flex-col gap-3">
      <Alert class="flex items-start gap-3">
        <FeaturedIconOutline kind="outline" color="warning" size="md" class="shrink-0" />
        <div class="space-y-1 text-left">
          <AlertTitle class="font-semibold">
            {{ $t('components.profile.quota-modal.restriction_title') }}
          </AlertTitle>
          <AlertDescription>
            {{ $t('components.profile.quota-modal.restriction_description') }}
            <strong>
              {{
                $t(`components.profile.quota-modal.restrictions.${data!.restriction_applied}`)
              }} </strong
            >.
          </AlertDescription>
        </div>
      </Alert>
      <div>
        <h3 class="font-semibold mt-2 mb-2 text-gray-warm-900 text-md">
          {{ $t('components.profile.quota-modal.storage_current_usage') }}
        </h3>
        <i18n-t keypath="components.profile.quota-modal.total_size" tag="span">
          <strong>{{ Math.round(totalPercent!) }}%</strong>
        </i18n-t>
        <div class="flex items-center gap-2">
          <Progress v-model="totalPercent" :class="['h-2', totalColor]" />
          <span v-if="total!.total === Infinity" class="whitespace-nowrap"
            >{{ total!.current.toFixed(1) }}GB&nbsp;/&nbsp;<Icon
              name="infinity"
              size="sm"
              class="inline mb-0.5"
              stroke-color=""
            />GB</span
          >
          <span v-else>{{ total!.current.toFixed(1) }}GB&nbsp;/&nbsp;{{ total!.total }}GB</span>
        </div>
      </div>
      <div class="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3 justify-items-center">
        <MetricItem
          v-for="{ name, icon, info } of metrics"
          :key="name"
          :title="$t(`components.profile.quota-modal.metrics.${name}`)"
          :icon="icon"
          class="w-full"
          v-bind="info"
        />
      </div>
    </div>
  </Modal>
</template>
