<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal } from '@/components/modal'
import { Icon } from '@/components/icon'
import { Progress } from '@/components/ui/progress'
import { DesktopStatusEnum, type GetDeploymentResponse } from '@/gen/oas/apiv4'
import { useBulkSpawnStore } from '@/stores/bulk-spawn'

// A desktop leaves storage provisioning however it turned out — Failed
// included, or a deployment with one bad disk would never fill the bar.
const PROVISIONED_STATUSES: string[] = [
  DesktopStatusEnum.STOPPED,
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.WAITING_IP,
  DesktopStatusEnum.FAILED
]

interface Props {
  open?: boolean
  deployment?: GetDeploymentResponse | null
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  deployment: null
})

const emit = defineEmits<(e: 'close') => void>()

const { t } = useI18n()

const bulkSpawnStore = useBulkSpawnStore()

// The engine brackets its fan-out with creating_desktops / end_creating_desktops,
// so stage 1 is known to be running before the first row reaches the deployment.
const isSpawning = computed(() => {
  const id = props.deployment?.info.id
  return !!id && bulkSpawnStore.deploymentsInProgress.has(id)
})

// len(create_dict) * total_users: what the deployment is aiming for, not the
// rows that exist right now, so the bars have a fixed denominator.
const desktopsTotal = computed(() => props.deployment?.info.total_desktops ?? 0)

const statuses = computed(() =>
  (props.deployment?.users ?? []).flatMap((user) => user.desktops_statuses ?? [])
)
const desktopsArrived = computed(() =>
  statuses.value.reduce((total, status) => total + status.amount, 0)
)
const desktopsProvisioned = computed(() =>
  statuses.value
    .filter((status) => PROVISIONED_STATUSES.includes(status.status))
    .reduce((total, status) => total + status.amount, 0)
)

const key = (name: string) => `views.deployment.provisioning-modal.${name}`

const stages = computed(() => {
  const total = desktopsTotal.value
  const arrived = desktopsArrived.value
  const provisioned = desktopsProvisioned.value

  // Storage tasks run in parallel with the fan-out, so stage 2 can advance
  // before stage 1 is done; each stage is judged against the total on its own.
  const spawnDone = total > 0 && !isSpawning.value && arrived >= total
  const storageDone = total > 0 && provisioned >= total

  return [
    {
      name: 'stage1',
      done: spawnDone,
      active: total > 0 && !spawnDone,
      value: Math.min(arrived, total),
      status:
        total === 0
          ? t(key('stage1-pending'))
          : spawnDone
            ? t(key('stage1-done'), { total })
            : t(key('stage1-progress'), { current: Math.min(arrived, total), total })
    },
    {
      name: 'stage2',
      done: storageDone,
      active: total > 0 && arrived > 0 && !storageDone,
      value: Math.min(provisioned, total),
      status:
        total === 0 || arrived === 0
          ? t(key('stage2-pending'))
          : storageDone
            ? t(key('stage2-done'), { total })
            : t(key('stage2-progress'), { current: Math.min(provisioned, total), total })
    }
  ]
})

type Stage = (typeof stages.value)[number]

const percent = (value: number) =>
  desktopsTotal.value > 0 ? Math.round((value / desktopsTotal.value) * 100) : 0

const stageIcon = (stage: Stage) => {
  if (stage.done) return 'check-circle'
  return stage.active ? 'loading-01' : 'clock'
}

const stageColor = (stage: Stage) => {
  if (stage.done) return 'success-600'
  return stage.active ? 'brand-600' : 'gray-warm-400'
}
</script>

<template>
  <Modal
    :open="props.open"
    size="lg"
    :title="t(key('title'), { name: props.deployment?.info.name ?? '' })"
    :description="t(key('description'))"
    @close="emit('close')"
  >
    <ul class="flex flex-col gap-6 pb-2">
      <li v-for="stage in stages" :key="stage.name" class="flex flex-col gap-1.5">
        <div class="flex flex-row items-center gap-2 text-sm">
          <Icon
            :name="stageIcon(stage)"
            class="h-4 w-4"
            :class="stage.active ? 'animate-spin' : ''"
            :stroke-color="stageColor(stage)"
          />
          <span class="font-medium text-gray-warm-800">{{ t(key(`${stage.name}-title`)) }}</span>
        </div>
        <span class="text-sm text-gray-warm-500">{{ stage.status }}</span>
        <Progress v-if="desktopsTotal > 0" :model-value="percent(stage.value)" class="h-2" />
      </li>
    </ul>
  </Modal>
</template>
