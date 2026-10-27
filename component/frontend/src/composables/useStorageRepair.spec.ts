import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  report: vi.fn(),
  handle: vi.fn(),
  fix: vi.fn(),
  toast: Object.assign(vi.fn(), {
    loading: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    dismiss: vi.fn()
  })
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: (key: string) => key.includes('not_allowed') })
}))
vi.mock('@/gen/oas/apiv4/', () => ({
  getDesktopStorageProblems: mocks.report,
  handleDesktopStorageProblems: mocks.handle,
  fixDesktopStorage: mocks.fix
}))
vi.mock('@/components/ui/toast', () => ({ toast: mocks.toast }))

import type { PlannedProblem } from '@/lib/storage-problems'
import { useStorageTasksStore } from '@/stores/storage-tasks'
import { useStorageRepair } from './useStorageRepair'

const zeros = (allowed: boolean) => ({
  code: 'storage_zeros',
  fix: 'dig_holes',
  mode: 'costly',
  blocks_start: false,
  allowed
})

const handled = (allowed = false) => ({
  desktop_id: 'd1',
  can_repair_costly: allowed,
  quick_fixes: [{ storage_id: 's1', fix: 'check', task_id: 't1' }],
  disks: [
    {
      storage_id: 's1',
      problems: [
        { code: 'storage_damaged', fix: 'check', mode: 'quick', blocks_start: true, allowed: true },
        zeros(allowed)
      ]
    }
  ]
})

const after = (allowed = false) => ({
  desktop_id: 'd1',
  can_repair_costly: allowed,
  disks: [{ storage_id: 's1', problems: [zeros(allowed)] }]
})

let desktops = 0
const nextDesktop = () => `d${++desktops}`

describe('useStorageRepair', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows the quick fix it ran and starts the desktop again once it ends', async () => {
    mocks.handle.mockResolvedValue({ data: handled() })
    mocks.report.mockResolvedValue({ data: after() })
    const retryStart = vi.fn()
    const repair = useStorageRepair()
    expect(
      await repair.diagnose({ desktopId: nextDesktop(), desktopName: 'win', retryStart })
    ).toBe(true)
    expect(repair.open.value).toBe(true)
    expect(repair.plan.value?.quickFixes).toEqual([
      { storage_id: 's1', fix: 'check', task_id: 't1' }
    ])
    expect(repair.plan.value?.quick).toEqual([])
    expect(repair.plan.value?.costly.map((i) => i.problem.allowed)).toEqual([false])
    expect(mocks.fix).not.toHaveBeenCalled()

    useStorageTasksStore().update({ id: 't1', status: 'finished' })
    await vi.waitFor(() => expect(retryStart).toHaveBeenCalledOnce())
    expect(repair.open.value).toBe(false)
  })

  it('does not start again when the quick fix failed', async () => {
    mocks.handle.mockResolvedValue({ data: handled() })
    mocks.report.mockResolvedValue({ data: after() })
    const retryStart = vi.fn()
    const repair = useStorageRepair()
    await repair.diagnose({ desktopId: nextDesktop(), desktopName: 'win', retryStart })
    useStorageTasksStore().update({ id: 't1', status: 'failed' })
    await vi.waitFor(() => expect(mocks.toast.error).toHaveBeenCalled())
    expect(retryStart).not.toHaveBeenCalled()
  })

  it('runs a costly repair only from the button, and says when the API forbids it', async () => {
    mocks.handle.mockResolvedValue({ data: handled(true) })
    const repair = useStorageRepair()
    await repair.diagnose({ desktopId: nextDesktop(), desktopName: 'win', retryStart: vi.fn() })
    const item = repair.plan.value?.costly[0] as PlannedProblem
    mocks.fix.mockRejectedValueOnce({ description_code: 'storage_repair_not_allowed' })
    await repair.confirm(item)
    expect(repair.errorMessage.value).toBe('api.storage-fix.errors.storage_repair_not_allowed')

    mocks.fix.mockResolvedValueOnce({ data: { task_id: 't2' } })
    await repair.confirm(item)
    expect(mocks.fix).toHaveBeenLastCalledWith({
      path: { desktop_id: expect.any(String), storage_id: 's1', fix: 'dig_holes' },
      throwOnError: true
    })
    expect(repair.isQueued(item)).toBe(true)
    expect(mocks.toast.success).toHaveBeenCalled()
  })

  it('leaves the start error alone when the disks have nothing', async () => {
    mocks.handle.mockResolvedValue({
      data: {
        desktop_id: 'd1',
        can_repair_costly: false,
        disks: [{ storage_id: 's1', problems: [] }]
      }
    })
    const repair = useStorageRepair()
    expect(
      await repair.diagnose({ desktopId: nextDesktop(), desktopName: 'win', retryStart: vi.fn() })
    ).toBe(false)
    expect(repair.open.value).toBe(false)
  })

  it('leaves the start error alone when the report fails', async () => {
    mocks.handle.mockRejectedValue(new Error('down'))
    const repair = useStorageRepair()
    expect(
      await repair.diagnose({ desktopId: nextDesktop(), desktopName: 'win', retryStart: vi.fn() })
    ).toBe(false)
  })
})
