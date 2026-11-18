import { beforeEach, describe, expect, it } from 'vitest'

import {
  addDesktopTimeout,
  clearDesktopTimeouts,
  desktopTimeouts,
  highestDesktopTimeoutLevel,
  parseDesktopTimeout,
  removeDesktopTimeoutsOf,
  removeDesktopTimeoutsSupersededBy,
  type DesktopTimeoutWarning
} from './desktop-timeout'

const warning = (overrides: Partial<DesktopTimeoutWarning> = {}): DesktopTimeoutWarning => ({
  key: 'd1',
  desktopId: 'd1',
  name: 'Desktop 1',
  stopsAt: '2026-11-18T10:00+0000',
  level: 'warning',
  extendMinutes: null,
  ...overrides
})

describe('desktop timeout warnings', () => {
  beforeEach(clearDesktopTimeouts)

  it('keeps the warnings of different desktops side by side', () => {
    addDesktopTimeout(warning())
    addDesktopTimeout(warning({ key: 'd2', desktopId: 'd2', name: 'Desktop 2' }))

    expect(desktopTimeouts.value.map((w) => w.key)).toEqual(['d1', 'd2'])
  })

  it('replaces the earlier warning of the same desktop', () => {
    addDesktopTimeout(warning({ level: 'warning' }))
    addDesktopTimeout(warning({ key: 'd2', desktopId: 'd2' }))
    addDesktopTimeout(warning({ level: 'danger' }))

    expect(desktopTimeouts.value.map((w) => [w.key, w.level])).toEqual([
      ['d1', 'danger'],
      ['d2', 'warning']
    ])
  })

  it('removes only the warnings of the given desktop', () => {
    addDesktopTimeout(warning())
    addDesktopTimeout(warning({ key: 'd2', desktopId: 'd2' }))

    removeDesktopTimeoutsOf('d1')

    expect(desktopTimeouts.value.map((w) => w.key)).toEqual(['d2'])
  })

  it('drops a warning once the desktop is scheduled to stop later than announced', () => {
    addDesktopTimeout(warning())
    addDesktopTimeout(warning({ key: 'd2', desktopId: 'd2' }))

    removeDesktopTimeoutsSupersededBy('d1', '2026-11-18T10:30+0000')

    expect(desktopTimeouts.value.map((w) => w.key)).toEqual(['d2'])
  })

  it.each([
    ['the same stop time', '2026-11-18T10:00+0000'],
    ['an earlier stop time', '2026-11-18T09:00+0000'],
    ['no scheduled stop', false],
    ['a missing value', undefined]
  ])('keeps the warning on %s', (_label, shutdown) => {
    addDesktopTimeout(warning())

    removeDesktopTimeoutsSupersededBy('d1', shutdown)

    expect(desktopTimeouts.value).toHaveLength(1)
  })

  it('reports the most severe level', () => {
    expect(highestDesktopTimeoutLevel([])).toBe('info')
    expect(
      highestDesktopTimeoutLevel([
        warning({ level: 'danger' }),
        warning({ level: 'info' }),
        warning({ level: 'warning' })
      ])
    ).toBe('danger')
  })
})

describe('parseDesktopTimeout', () => {
  const payload = (params: Record<string, unknown>, type = 'warning') => ({
    type,
    msg_code: 'desktop-time-limit',
    params
  })

  it('ignores other messages', () => {
    expect(parseDesktopTimeout({ type: 'info', msg_code: 'other', params: {} })).toBeNull()
  })

  it('keys the warning by desktop', () => {
    const parsed = parseDesktopTimeout(
      payload({
        date: '2026-11-18T10:00+0000',
        name: 'Desktop 1',
        desktop_id: 'd1',
        extend_enabled: true,
        extend_time: 30
      })
    )

    expect(parsed).toEqual({
      key: 'd1',
      desktopId: 'd1',
      name: 'Desktop 1',
      stopsAt: '2026-11-18T10:00+0000',
      level: 'warning',
      extendMinutes: 30
    })
  })

  it('still tells desktops apart when the payload carries no desktop id', () => {
    const first = parseDesktopTimeout(payload({ date: '2026-11-18T10:00+0000', name: 'A' }))
    const second = parseDesktopTimeout(payload({ date: '2026-11-18T10:00+0000', name: 'B' }))

    expect(first?.desktopId).toBeNull()
    expect(first?.extendMinutes).toBeNull()
    expect(first?.key).not.toBe(second?.key)
  })
})
