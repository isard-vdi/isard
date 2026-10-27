export type StorageFix =
  | 'check'
  | 'check_backing_chain'
  | 'repair_leaks'
  | 'repair_all'
  | 'dig_holes'
  | 'sparsify'
export type StorageProblemMode = 'wait' | 'quick' | 'costly' | 'admin'

export interface StorageFixEstimate {
  tier?: string | null
  ahead?: number | null
  wait_seconds?: number | null
  run_seconds?: number | null
  basis?: string | null
  stranded?: boolean | null
}

export interface StorageProblemItem {
  code: string
  fix?: StorageFix | null
  blocks_start?: boolean
  mode: StorageProblemMode
  allowed?: boolean
  estimate?: StorageFixEstimate | null
}

export interface StorageRunningTask {
  id: string
  status?: string | null
  progress?: number | null
  position?: number | null
  eta_seconds?: number | null
  stranded?: boolean | null
}

export interface StorageDiskProblems {
  storage_id: string
  status?: string | null
  size?: number | null
  problems: StorageProblemItem[]
  task?: StorageRunningTask | null
}

export interface StorageQuickFixRun {
  storage_id: string
  fix: StorageFix
  task_id?: string | null
  refused?: string | null
  recorded?: string | null
}

export interface StorageProblemsReport {
  desktop_id: string
  can_repair_costly: boolean
  disks: StorageDiskProblems[]
  quick_fixes?: StorageQuickFixRun[]
}

export interface PlannedProblem {
  storageId: string
  problem: StorageProblemItem
  task?: StorageRunningTask | null
}

export interface StorageRepairPlan {
  quickFixes: StorageQuickFixRun[]
  waits: PlannedProblem[]
  quick: PlannedProblem[]
  costly: PlannedProblem[]
  admins: PlannedProblem[]
}

export const TASK_DONE = ['finished', 'failed', 'canceled']

/** Start errors that may come from a disk; the report decides whether one did. */
export const STORAGE_START_ERROR_CODES = ['desktop_storage_not_ready', 'storage_not_found']

const SECTION: Record<StorageProblemMode, 'waits' | 'quick' | 'costly' | 'admins'> = {
  wait: 'waits',
  quick: 'quick',
  costly: 'costly',
  admin: 'admins'
}

export function planStorageProblems(report: StorageProblemsReport): StorageRepairPlan {
  const plan: StorageRepairPlan = {
    quickFixes: report.quick_fixes ?? [],
    waits: [],
    quick: [],
    costly: [],
    admins: []
  }
  const queued = new Set(
    plan.quickFixes.filter((run) => run.task_id).map((run) => `${run.storage_id}:${run.fix}`)
  )
  for (const disk of report.disks) {
    for (const problem of disk.problems) {
      if (queued.has(`${disk.storage_id}:${problem.fix}`)) continue
      // a quick fix already running on the disk is waited for, not offered again
      const section = disk.task && problem.mode === 'quick' ? 'waits' : SECTION[problem.mode]
      plan[section].push({ storageId: disk.storage_id, problem, task: disk.task })
    }
  }
  return plan
}

export function hasStorageProblems(plan: StorageRepairPlan): boolean {
  return Object.values(plan).some((items) => items.length > 0)
}

export function blocksStart(plan: StorageRepairPlan): boolean {
  return [plan.waits, plan.quick, plan.costly, plan.admins].some((items) =>
    items.some((item) => item.problem.blocks_start !== false)
  )
}

/** The tasks this plan waits on: the quick fixes it queued and the ones holding a disk. */
export function pendingTaskIds(plan: StorageRepairPlan): string[] {
  const ids = plan.quickFixes.map((run) => run.task_id).filter((id): id is string => !!id)
  for (const item of plan.waits) if (item.task?.id) ids.push(item.task.id)
  return [...new Set(ids)]
}

export function totalSeconds(estimate?: StorageFixEstimate | null): number | null {
  if (!estimate || estimate.run_seconds == null) return null
  return estimate.run_seconds + (estimate.wait_seconds ?? 0)
}

/** A rounded duration and the unit key it is in: `s`, `min` or `h`. */
export function roundDuration(seconds: number): { value: number; unit: 's' | 'min' | 'h' } {
  if (seconds < 60) return { value: Math.max(1, Math.round(seconds)), unit: 's' }
  if (seconds < 3600) return { value: Math.round(seconds / 60), unit: 'min' }
  return { value: Math.round((seconds / 3600) * 10) / 10, unit: 'h' }
}
