import { describe, expect, it } from 'vitest'

import { isRunning, runningCount, type MatrixDesktop } from './deployment-visibility'

const desktop = (status: string | null): MatrixDesktop => ({
  desktop_id: `desktop-${status}`,
  visible: true,
  status
})

describe('isRunning', () => {
  it('counts every status the API would stop', () => {
    expect(isRunning(desktop('Started'))).toBe(true)
    expect(isRunning(desktop('Starting'))).toBe(true)
    expect(isRunning(desktop('StartingPaused'))).toBe(true)
    expect(isRunning(desktop('Shutting-down'))).toBe(true)
  })

  it('leaves out the ones hiding cannot interrupt', () => {
    expect(isRunning(desktop('Stopped'))).toBe(false)
    expect(isRunning(desktop('Failed'))).toBe(false)
    expect(isRunning(desktop(null))).toBe(false)
    expect(isRunning(undefined)).toBe(false)
  })
})

describe('runningCount', () => {
  it('is what the confirmation offers to stop', () => {
    expect(runningCount([desktop('Started'), desktop('Stopped'), desktop('Starting')])).toBe(2)
    expect(runningCount([])).toBe(0)
  })
})
