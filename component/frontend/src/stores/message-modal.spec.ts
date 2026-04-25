import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useMessageModalStore } from './message-modal'

describe('message-modal store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts closed with default warning level', () => {
    const store = useMessageModalStore()
    expect(store.open).toBe(false)
    expect(store.msgCode).toBe('')
    expect(store.level).toBe('warning')
    expect(store.params).toEqual({})
  })

  it('opens the modal when show() is called', () => {
    const store = useMessageModalStore()
    store.show('info', 'searching-resources', {})
    expect(store.open).toBe(true)
    expect(store.msgCode).toBe('searching-resources')
    expect(store.level).toBe('info')
  })

  it.each([
    ['warning', 'warning'],
    ['danger', 'danger'],
    ['info', 'info'],
    ['success', 'success']
  ] as const)('maps payload type %s to level %s', (type, expected) => {
    const store = useMessageModalStore()
    store.show(type, 'desktop-time-limit', {})
    expect(store.level).toBe(expected)
  })

  it('falls back to warning for unknown or null type', () => {
    const store = useMessageModalStore()
    store.show(null, 'searching-resources', {})
    expect(store.level).toBe('warning')

    store.show('not-a-real-level', 'searching-resources', {})
    expect(store.level).toBe('warning')
  })

  it('formats ISO date params into a locale-aware HH:MM time string', () => {
    const store = useMessageModalStore()
    store.show('warning', 'desktop-time-limit', { date: '2026-04-25T14:30:00Z' })
    expect(typeof store.params.date).toBe('string')
    expect(store.params.date).not.toBe('2026-04-25T14:30:00Z')
    expect(store.params.date).toMatch(/\d{1,2}:\d{2}/)
  })

  it('leaves invalid date strings untouched', () => {
    const store = useMessageModalStore()
    store.show('warning', 'desktop-time-limit', { date: 'not-a-date' })
    expect(store.params.date).toBe('not-a-date')
  })

  it('exposes desktopId / extendTime / extendEnabled from params', () => {
    const store = useMessageModalStore()
    store.show('warning', 'desktop-time-limit', {
      desktop_id: 'abc',
      extend_enabled: true,
      extend_time: 30
    })
    expect(store.desktopId).toBe('abc')
    expect(store.extendEnabled).toBe(true)
    expect(store.extendTime).toBe(30)
  })

  it('canExtend is true only for desktop-time-limit with desktop_id + extend_enabled', () => {
    const store = useMessageModalStore()

    store.show('warning', 'desktop-time-limit', {
      desktop_id: 'abc',
      extend_enabled: true,
      extend_time: 30
    })
    expect(store.canExtend).toBe(true)

    store.show('warning', 'desktop-time-limit', {
      desktop_id: 'abc',
      extend_enabled: false,
      extend_time: 30
    })
    expect(store.canExtend).toBe(false)

    store.show('warning', 'desktop-time-limit', { extend_enabled: true, extend_time: 30 })
    expect(store.canExtend).toBe(false)

    store.show('warning', 'searching-resources', {
      desktop_id: 'abc',
      extend_enabled: true,
      extend_time: 30
    })
    expect(store.canExtend).toBe(false)
  })

  it('hide() closes the modal but preserves params for follow-up reads', () => {
    const store = useMessageModalStore()
    store.show('warning', 'desktop-time-limit', { desktop_id: 'abc' })
    store.hide()
    expect(store.open).toBe(false)
    expect(store.msgCode).toBe('desktop-time-limit')
  })

  it('$reset clears all state to defaults', () => {
    const store = useMessageModalStore()
    store.show('danger', 'desktop-time-limit', { desktop_id: 'abc' })
    store.$reset()
    expect(store.open).toBe(false)
    expect(store.msgCode).toBe('')
    expect(store.level).toBe('warning')
    expect(store.params).toEqual({})
  })
})
