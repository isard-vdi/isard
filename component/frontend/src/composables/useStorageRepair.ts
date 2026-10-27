import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  fixDesktopStorage,
  getDesktopStorageProblems,
  handleDesktopStorageProblems
} from '@/gen/oas/apiv4/'
import { toast } from '@/components/ui/toast'
import { describeApiError } from '@/lib/api-errors'
import {
  TASK_DONE,
  blocksStart,
  hasStorageProblems,
  pendingTaskIds,
  planStorageProblems,
  roundDuration,
  totalSeconds,
  type PlannedProblem,
  type StorageFix,
  type StorageFixEstimate,
  type StorageProblemsReport,
  type StorageRepairPlan
} from '@/lib/storage-problems'
import { useStorageTasksStore } from '@/stores/storage-tasks'

export interface StorageRepairTarget {
  desktopId: string
  desktopName: string
  retryStart: () => void
}

export const WAIT_POLL_MS = 5000
export const RETRY_COOLDOWN_MS = 5 * 60_000

// shared by every view, so a start retried from one is not retried again from another
const lastRetry = new Map<string, number>()

export function useStorageRepair() {
  const { t, te } = useI18n()
  const tasks = useStorageTasksStore()

  const target = ref<StorageRepairTarget | null>(null)
  const plan = ref<StorageRepairPlan | null>(null)
  const open = ref(false)
  const watched = ref<string[]>([])
  const queuedHere = ref<Record<string, string>>({})
  const errorMessage = ref<string | null>(null)
  let failed = false
  let poll: ReturnType<typeof setInterval> | null = null

  const duration = (seconds: number | null | undefined) => {
    if (seconds == null) return t('components.storage-problems.duration.unknown')
    const { value, unit } = roundDuration(seconds)
    return t(`components.storage-problems.duration.${unit}`, { value })
  }

  const describeEstimate = (estimate?: StorageFixEstimate | null) =>
    t('components.storage-problems.estimate', {
      tier: t(`components.storage-problems.tier.${estimate?.tier ?? 'standard'}`),
      ahead: estimate?.ahead ?? 0,
      duration: duration(totalSeconds(estimate))
    })

  const key = (item: PlannedProblem) => `${item.storageId}:${item.problem.fix}`

  function stopPolling() {
    if (poll) clearInterval(poll)
    poll = null
  }

  function apply(report: StorageProblemsReport) {
    const next = planStorageProblems(report)
    plan.value = next
    watched.value = [...new Set([...pendingTaskIds(next), ...Object.values(queuedHere.value)])]
    if (watched.value.length && !poll) poll = setInterval(refresh, WAIT_POLL_MS)
    if (!watched.value.length) stopPolling()
    return next
  }

  async function refresh() {
    const current = target.value
    if (!current) return
    let next: StorageRepairPlan
    try {
      const { data } = await getDesktopStorageProblems({
        path: { desktop_id: current.desktopId },
        throwOnError: true
      })
      next = apply(data as StorageProblemsReport)
    } catch {
      return
    }
    if (watched.value.some((id) => !TASK_DONE.includes(tasks.tasks[id]?.status ?? ''))) return
    if (blocksStart(next) || failed) return
    stopPolling()
    open.value = false
    lastRetry.set(current.desktopId, Date.now())
    toast.success(t('components.storage-problems.fixed', { name: current.desktopName }))
    current.retryStart()
  }

  /** Handle the disk problems behind a failed start; false when there are none. */
  async function diagnose(next: StorageRepairTarget): Promise<boolean> {
    stopPolling()
    target.value = next
    queuedHere.value = {}
    errorMessage.value = null
    failed = false
    let found: StorageRepairPlan
    try {
      const { data } = await handleDesktopStorageProblems({
        path: { desktop_id: next.desktopId },
        throwOnError: true
      })
      found = apply(data as StorageProblemsReport)
    } catch {
      return false
    }
    if (!hasStorageProblems(found)) return false
    // nothing left blocks a start that was just retried: the cause is elsewhere
    const retriedAt = lastRetry.get(next.desktopId) ?? 0
    if (!blocksStart(found) && !watched.value.length && Date.now() - retriedAt < RETRY_COOLDOWN_MS)
      return false
    open.value = true
    return true
  }

  async function confirm(item: PlannedProblem) {
    const current = target.value
    if (!current || !item.problem.fix) return
    errorMessage.value = null
    try {
      const { data } = await fixDesktopStorage({
        path: {
          desktop_id: current.desktopId,
          storage_id: item.storageId,
          fix: item.problem.fix as StorageFix
        },
        throwOnError: true
      })
      queuedHere.value = { ...queuedHere.value, [key(item)]: data.task_id }
      watched.value = [...new Set([...watched.value, data.task_id])]
      if (!poll) poll = setInterval(refresh, WAIT_POLL_MS)
      toast.success(
        t('components.storage-problems.fix-queued', {
          fix: t(`components.storage-problems.fix.${item.problem.fix}`),
          name: current.desktopName
        }),
        { description: describeEstimate(data.estimate) }
      )
    } catch (error) {
      errorMessage.value = describeApiError(error, { t, te }, 'storage-fix')
    }
  }

  function close() {
    stopPolling()
    open.value = false
  }

  watch(
    () => watched.value.map((id) => tasks.tasks[id]?.status),
    async (statuses) => {
      if (!watched.value.length || !statuses.every((s) => s && TASK_DONE.includes(s))) return
      if (watched.value.some((id) => tasks.tasks[id]?.status !== 'finished')) {
        failed = true
        toast.error(t('components.storage-problems.failed', { name: target.value?.desktopName }))
      }
      await refresh()
    }
  )

  onScopeDispose(stopPolling)

  return {
    open,
    plan,
    target,
    errorMessage,
    diagnose,
    confirm,
    close,
    refresh,
    duration,
    describeEstimate,
    taskOf: (id?: string | null) => (id ? tasks.tasks[id] : undefined),
    isQueued: (item: PlannedProblem) => key(item) in queuedHere.value
  }
}
