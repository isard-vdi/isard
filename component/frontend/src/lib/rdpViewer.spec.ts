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

  it('blocks RDP while the guest RDP is not verified, unless the user may bypass it', () => {
    const rdp = { state: 'waiting' }
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', rdp, false, t)).toMatchObject({
      loading: true,
      status: 'waiting',
      tone: 'wait'
    })
    expect(rdpViewerEntry('file-rdpgw', '10.2.0.5', rdp, true, t)).toMatchObject({
      loading: false,
      status: 'waiting'
    })
  })

  it('marks refused credentials as an error', () => {
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'auth_failed' }, false, t)
    ).toMatchObject({ loading: true, status: 'auth_failed', tone: 'error' })
  })

  it('opens an unverified RDP with an informative status', () => {
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'unverified' }, false, t)
    ).toMatchObject({ loading: false, status: 'unverified', tone: 'info' })
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
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: evil }, false, tt)
    ).toMatchObject({ status: undefined })
  })

  it('shows a translated sentence for the reason, never the internal code', () => {
    const named: Record<string, unknown>[] = []
    const tt = (key: string, n?: Record<string, unknown>) => {
      if (n) named.push(n)
      return key
    }
    rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'refused', reason: 'tls_not_allowed' }, false, tt)
    expect(named.at(-1)).toEqual({ reason: 'components.desktops.desktop-card.rdp.reason.tls_not_allowed' })
    rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'refused', reason: 'certificate_missing' }, false, tt)
    expect(named.at(-1)).toEqual({ reason: 'components.desktops.desktop-card.rdp.reason.certificate' })
    rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'refused', reason: 'negotiation_failure_9' }, false, tt)
    expect(named.at(-1)).toEqual({ reason: 'components.desktops.desktop-card.rdp.reason.other' })
    expect(
      rdpViewerEntry('browser-rdp', '10.2.0.5', { state: 'auth_failed', reason: 'account_blocked' }, false, tt).status
    ).toBe('components.desktops.desktop-card.rdp.reason.account_blocked')
  })
})
