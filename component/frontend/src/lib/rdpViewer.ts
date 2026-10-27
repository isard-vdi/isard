import type { Viewer } from '@/components/viewer-select'

export interface DesktopRdp {
  state: string
  // security the guest negotiated: rdp (standard RDP security), tls or nla
  protocol?: string | null
  reason?: string | null
  last?: { connected?: boolean; result?: string | null } | null
}

// States the vpn writes; any other value is not shown.
const RDP_STATES = ['pending', 'waiting', 'verifying', 'refused', 'auth_failed', 'unverified']

// The vpn writes the reason as an internal code. The user gets a translated
// sentence picked by key; an unknown code falls back to a generic one and is
// never shown as it came.
const REASON_KEYS: Record<string, string> = {
  port_closed: 'port_closed',
  unreachable: 'unreachable',
  not_rdp: 'not_rdp',
  tls_required: 'tls_required',
  tls_not_allowed: 'tls_not_allowed',
  nla_required: 'nla_required',
  certificate_missing: 'certificate',
  certificate_not_allowed: 'certificate',
  security_refused: 'security_refused',
  account_blocked: 'account_blocked',
  no_credentials: 'no_credentials',
  security_not_allowed: 'security_not_allowed'
}

const reasonKey = (reason?: string | null) =>
  (typeof reason === 'string' && Object.prototype.hasOwnProperty.call(REASON_KEYS, reason)
    ? REASON_KEYS[reason]
    : 'other') as string

// States in which the server already lets anybody open an RDP viewer.
const RDP_OPEN_STATES = ['ready', 'unverified']

// How far the check has got (IP -> RDP port -> credentials), to fill the button; open is full.
const RDP_PROGRESS: Record<string, number> = {
  pending: 25,
  waiting: 50,
  refused: 50,
  verifying: 80,
  auth_failed: 80,
  unverified: 100,
  ready: 100
}

type Translate = (key: string, named?: Record<string, unknown>) => string

/**
 * Turn a desktop's IP and RDP verification state into the viewer entry the
 * viewer buttons render: an RDP viewer is "loading" (blocked) until the guest
 * has an IP and its RDP has been verified -- unless the user may bypass the
 * check -- and carries the step it is in as ``status`` plus how far the check
 * has got as ``progress``, so the card can show it on the button instead of
 * growing a line of text. ``unverified`` (no NLA, no stored credentials or a
 * check that could not run) opens with a warning, never a hard block: a probe
 * that fails must not cut the service.
 */
export function rdpViewerEntry(
  viewer: string,
  ip: string | null | undefined,
  rdp: DesktopRdp | null | undefined,
  bypass: boolean,
  t: Translate
): Viewer {
  if (!viewer.includes('rdp')) return { id: viewer, loading: false }
  if (!ip) {
    return {
      id: viewer,
      loading: true,
      status: t('components.desktops.desktop-card.rdp.waiting_ip'),
      tone: 'wait',
      progress: 10
    }
  }
  if (!rdp) return { id: viewer, loading: false }
  const blocked = !RDP_OPEN_STATES.includes(rdp.state)
  const lastFailed = !blocked && !!rdp.last && !rdp.last.connected
  const refused = ['refused', 'auth_failed'].includes(rdp.state)
  let status = ''
  let tone: Viewer['tone'] | undefined
  if (lastFailed) {
    status = t(
      rdp.last?.result === 'auth_failed'
        ? 'components.desktops.desktop-card.rdp.auth_failed'
        : 'components.desktops.desktop-card.rdp.last_failed'
    )
    tone = 'error'
  } else if (rdp.state === 'auth_failed' && rdp.reason === 'account_blocked') {
    status = t('components.desktops.desktop-card.rdp.reason.account_blocked')
    tone = 'error'
  } else if (rdp.state === 'refused' && rdp.reason === 'security_not_allowed') {
    // the guest answers, but with a security level the administrator does not allow
    status = t('components.desktops.desktop-card.rdp.security_not_allowed', {
      reason: t('components.desktops.desktop-card.rdp.reason.security_not_allowed')
    })
    tone = 'error'
  } else if (rdp.state === 'unverified' && rdp.protocol === 'rdp') {
    // standard RDP security has no credential check to run before connecting
    status = t('components.desktops.desktop-card.rdp.unverified_standard')
    tone = 'warn'
  } else if (rdp.state === 'unverified' && rdp.reason === 'no_credentials') {
    status = t('components.desktops.desktop-card.rdp.reason.no_credentials')
    tone = 'warn'
  } else if (rdp.state === 'unverified') {
    status = t('components.desktops.desktop-card.rdp.unverified')
    tone = 'warn'
  } else if (RDP_STATES.includes(rdp.state)) {
    status = t(`components.desktops.desktop-card.rdp.${rdp.state}`, {
      reason: t(`components.desktops.desktop-card.rdp.reason.${reasonKey(rdp.reason)}`)
    })
    tone = refused ? 'error' : 'wait'
  }
  return {
    id: viewer,
    loading: blocked && !bypass,
    status: status || undefined,
    tone: status ? tone : undefined,
    progress: status ? (RDP_PROGRESS[rdp.state] ?? (blocked ? 50 : 100)) : undefined
  }
}
