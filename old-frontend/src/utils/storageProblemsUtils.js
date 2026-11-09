// The disk problems of a desktop that cannot start, grouped by how each one is
// handled. Same logic as the new frontend's lib/storage-problems.ts.

export const TASK_DONE = ['finished', 'failed', 'canceled']

// Start errors that may come from a disk; the report decides whether one did.
export const STORAGE_START_ERROR_CODES = ['desktop_storage_not_ready', 'storage_not_found']

const SECTION = {
  wait: 'waits',
  quick: 'quick',
  costly: 'costly',
  admin: 'admins'
}

export function planStorageProblems (report) {
  const plan = {
    quickFixes: report.quick_fixes || [],
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

export function hasStorageProblems (plan) {
  return Object.values(plan).some((items) => items.length > 0)
}

export function blocksStart (plan) {
  return [plan.waits, plan.quick, plan.costly, plan.admins].some((items) =>
    items.some((item) => item.problem.blocks_start !== false)
  )
}

// The tasks this plan waits on: the quick fixes it queued and the ones holding a disk.
export function pendingTaskIds (plan) {
  const ids = plan.quickFixes.map((run) => run.task_id).filter((id) => !!id)
  for (const item of plan.waits) if (item.task && item.task.id) ids.push(item.task.id)
  return [...new Set(ids)]
}

export function totalSeconds (estimate) {
  if (!estimate || estimate.run_seconds == null) return null
  return estimate.run_seconds + (estimate.wait_seconds || 0)
}

// A rounded duration and the unit key it is in: `s`, `min` or `h`.
export function roundDuration (seconds) {
  if (seconds < 60) return { value: Math.max(1, Math.round(seconds)), unit: 's' }
  if (seconds < 3600) return { value: Math.round(seconds / 60), unit: 'min' }
  return { value: Math.round((seconds / 3600) * 10) / 10, unit: 'h' }
}
