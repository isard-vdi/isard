import { describe, expect, it } from 'vitest'
import { rdpViewerEntry } from './rdpViewer'

const t = (key: string) => key.split('.').pop() as string

describe('rdpViewerEntry', () => {
  it('leaves non-RDP viewers alone', () => {
    expect(rdpViewerEntry('browser-vnc', null, null, false, t)).toEqual({
      id: 'browser-vnc',
      loading: false
    })
  })

  it('blocks RDP while the desktop has no IP and says so', () => {
    expect(rdpViewerEntry('browser-rdp', null, null, false, t)).toMatchObject({
      loading: true,
      status: 'waiting_ip',
      tone: 'wait'
    })
  })

  it('blocks RDP while the check runs, for those who may bypass it too', () => {
    const rdp = { state: 'waiting' }
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', rdp, false, t)).toMatchObject({
      loading: true,
      status: 'waiting',
      tone: 'wait'
    })
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', rdp, true, t)).toMatchObject({
      loading: true,
      status: 'waiting'
    })
  })

  it('lets those who may bypass it open a refused RDP', () => {
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', { state: 'refused' }, true, t)).toMatchObject({
      loading: false,
      tone: 'error'
    })
  })

  it('marks refused credentials as an error', () => {
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'auth_failed' }, false, t)
    ).toMatchObject({ loading: true, status: 'auth_failed', tone: 'error' })
  })

  it('opens an unverified RDP with a warning, never a block (a failed probe must not cut the service)', () => {
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'unverified' }, true, t, true)
    ).toMatchObject({ loading: false, status: 'unverified', tone: 'warn', progress: undefined })
  })

  it('opens an unverified RDP for a user or a manager with no warning', () => {
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'unverified', protocol: 'rdp' }, false, t)
    ).toMatchObject({ loading: false, status: undefined, tone: undefined, progress: undefined })
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'unverified', protocol: 'rdp' }, true, t)
    ).toMatchObject({ loading: false, status: undefined, tone: undefined })
  })

  it('opens a guest with standard RDP security with its own warning', () => {
    expect(
      rdpViewerEntry(
        'file-rdpgw',
        '10.2.0.5',
        { state: 'unverified', protocol: 'rdp' },
        true,
        t,
        true
      )
    ).toMatchObject({
      loading: false,
      status: 'unverified_standard',
      tone: 'warn',
      progress: undefined
    })
    // without stored credentials too: there is nothing to check them against
    expect(
      rdpViewerEntry(
        'file-rdpgw',
        '10.2.0.5',
        { state: 'unverified', protocol: 'rdp', reason: 'no_credentials' },
        true,
        t,
        true
      )
    ).toMatchObject({ status: 'unverified_standard', tone: 'warn' })
  })

  it('blocks a security level the administrator does not allow and says why', () => {
    const rdp = { state: 'refused', protocol: 'rdp', reason: 'security_not_allowed' }
    expect(rdpViewerEntry('browser-rdp', '10.2.0.5', rdp, false, t)).toMatchObject({
      loading: true,
      status: 'security_not_allowed',
      tone: 'error'
    })
    expect(rdpViewerEntry('browser-rdp', '10.2.0.5', rdp, true, t)).toMatchObject({
      loading: false
    })
  })

  it('shows "credentials not verified" as a blocking step while the check runs', () => {
    expect(
      rdpViewerEntry('file-rdpgw', '10.2.0.5', { state: 'verifying' }, false, t)
    ).toMatchObject({ loading: true, status: 'verifying', tone: 'wait', progress: 80 })
    // an admin/manager waits for the check too
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', { state: 'verifying' }, true, t)).toMatchObject(
      { loading: true, status: 'verifying', tone: 'wait', progress: 80 }
    )
  })

  it('fills the button background left to right as the check advances', () => {
    const progress = (ip: string | null, state?: string) =>
      rdpViewerEntry('file-rdpgw', ip, state ? { state } : null, false, t).progress
    expect(progress(null)).toBe(10) // waiting for IP
    expect(progress('10.2.0.5', 'pending')).toBe(25)
    expect(progress('10.2.0.5', 'waiting')).toBe(50)
    expect(progress('10.2.0.5', 'verifying')).toBe(80)
    expect(progress('10.2.0.5', 'ready')).toBeUndefined() // ready: plain active button
    expect(progress('10.2.0.5', 'unverified')).toBeUndefined() // warning: no fill
    expect(progress('10.2.0.5', 'auth_failed')).toBeUndefined() // error: no fill
  })

  it('opens a ready RDP with no status, and flags a failed last connection', () => {
    expect(rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'ready' }, false, t)).toEqual({
      id: 'browser-rdp',
      loading: false,
      status: undefined,
      tone: undefined
    })
    expect(
      rdpViewerEntry(
        'browser-rdp',
        '10.2.0.5',
        { state: 'ready', last: { connected: false, result: 'auth_failed' } },
        false,
        t
      )
    ).toMatchObject({ loading: false, status: 'auth_failed', tone: 'error' })
  })

  it('never shows a reason or a state that is not one of the fixed words', () => {
    const named: Record<string, unknown>[] = []
    const tt = (key: string, n?: Record<string, unknown>) => {
      named.push(n || {})
      return key.split('.').pop() as string
    }
    const evil = '<img src=x onerror=alert(1)>'
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'refused', reason: evil }, false, tt)
    ).toMatchObject({ status: 'refused' })
    expect(named.at(-1)).toEqual({ reason: 'other' })
    expect(rdpViewerEntry('browser-rdp', '10.2.0.5', { state: evil }, false, tt)).toMatchObject({
      status: undefined
    })
  })

  it('shows a translated sentence for the reason, never the internal code', () => {
    const named: Record<string, unknown>[] = []
    const tt = (key: string, n?: Record<string, unknown>) => {
      if (n) named.push(n)
      return key
    }
    rdpViewerEntry(
      'browser-rdp',
      '10.2.0.5',
      { state: 'refused', reason: 'tls_not_allowed' },
      false,
      tt
    )
    expect(named.at(-1)).toEqual({
      reason: 'components.desktops.desktop-card.rdp.reason.tls_not_allowed'
    })
    rdpViewerEntry(
      'browser-rdp',
      '10.2.0.5',
      { state: 'refused', reason: 'certificate_missing' },
      false,
      tt
    )
    expect(named.at(-1)).toEqual({
      reason: 'components.desktops.desktop-card.rdp.reason.certificate'
    })
    rdpViewerEntry(
      'browser-rdp',
      '10.2.0.5',
      { state: 'refused', reason: 'negotiation_failure_9' },
      false,
      tt
    )
    expect(named.at(-1)).toEqual({ reason: 'components.desktops.desktop-card.rdp.reason.other' })
    expect(
      rdpViewerEntry(
        'browser-rdp',
        '10.2.0.5',
        { state: 'auth_failed', reason: 'account_blocked' },
        false,
        tt
      ).status
    ).toBe('components.desktops.desktop-card.rdp.reason.account_blocked')
  })
})
