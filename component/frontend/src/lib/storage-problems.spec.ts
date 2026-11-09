import { describe, expect, it } from 'vitest'

import {
  blocksStart,
  hasStorageProblems,
  pendingTaskIds,
  planStorageProblems,
  roundDuration,
  totalSeconds,
  type StorageProblemsReport
} from './storage-problems'

const report = (over: Partial<StorageProblemsReport> = {}): StorageProblemsReport => ({
  desktop_id: 'd1',
  can_repair_costly: false,
  disks: [
    {
      storage_id: 's1',
      task: { id: 't9', progress: 0.5 },
      problems: [{ code: 'storage_busy', mode: 'wait', blocks_start: true }]
    },
    {
      storage_id: 's2',
      problems: [
        { code: 'storage_leaks', fix: 'repair_leaks', mode: 'quick', blocks_start: false },
        { code: 'storage_damaged', fix: 'repair_all', mode: 'costly', allowed: false },
        { code: 'storage_review_damage', mode: 'admin', blocks_start: true }
      ]
    }
  ],
  ...over
})

describe('planStorageProblems', () => {
  it('groups each problem by how it is handled', () => {
    const plan = planStorageProblems(report())
    expect(plan.waits.map((i) => i.storageId)).toEqual(['s1'])
    expect(plan.quick.map((i) => i.problem.fix)).toEqual(['repair_leaks'])
    expect(plan.costly.map((i) => i.problem.fix)).toEqual(['repair_all'])
    expect(plan.admins.map((i) => i.problem.code)).toEqual(['storage_review_damage'])
    expect(blocksStart(plan)).toBe(true)
  })

  it('moves a quick fix this call queued out of the pending ones', () => {
    const plan = planStorageProblems(
      report({ quick_fixes: [{ storage_id: 's2', fix: 'repair_leaks', task_id: 't1' }] })
    )
    expect(plan.quick).toEqual([])
    expect(pendingTaskIds(plan)).toEqual(['t1', 't9'])
  })

  it('keeps a quick fix left for the sweep among the pending ones', () => {
    const plan = planStorageProblems(
      report({ quick_fixes: [{ storage_id: 's2', fix: 'repair_leaks', recorded: 'repair_leaks' }] })
    )
    expect(plan.quick).toHaveLength(1)
    expect(pendingTaskIds(plan)).toEqual(['t9'])
  })

  it('waits for a disk task instead of offering a quick fix on that disk', () => {
    const plan = planStorageProblems(
      report({
        disks: [
          {
            storage_id: 's2',
            task: { id: 't5' },
            problems: [{ code: 'storage_leaks', fix: 'repair_leaks', mode: 'quick' }]
          }
        ]
      })
    )
    expect(plan.quick).toEqual([])
    expect(plan.waits.map((i) => i.task?.id)).toEqual(['t5'])
    expect(pendingTaskIds(plan)).toEqual(['t5'])
  })

  it('has nothing for clean disks, and non-blocking problems never block', () => {
    const clean = planStorageProblems(report({ disks: [{ storage_id: 's1', problems: [] }] }))
    expect(hasStorageProblems(clean)).toBe(false)
    const minor = planStorageProblems(
      report({
        disks: [
          {
            storage_id: 's1',
            problems: [
              { code: 'storage_zeros', fix: 'dig_holes', mode: 'costly', blocks_start: false }
            ]
          }
        ]
      })
    )
    expect(hasStorageProblems(minor)).toBe(true)
    expect(blocksStart(minor)).toBe(false)
  })
})

describe('durations', () => {
  it('adds the wait to the run and rounds to a unit', () => {
    expect(totalSeconds({ run_seconds: 30, wait_seconds: 90 })).toBe(120)
    expect(totalSeconds({ wait_seconds: 90 })).toBeNull()
    expect(roundDuration(0.2)).toEqual({ value: 1, unit: 's' })
    expect(roundDuration(150)).toEqual({ value: 3, unit: 'min' })
    expect(roundDuration(5400)).toEqual({ value: 1.5, unit: 'h' })
  })
})
