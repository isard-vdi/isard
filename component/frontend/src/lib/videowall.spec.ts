import { describe, expect, it } from 'vitest'

import type { UserDeploymentDesktop } from '@/gen/oas/apiv4'
import {
  groupVideowallDesktops,
  isRunning,
  toVideowallDesktop,
  videowallDesktopKey
} from './videowall'

const desktop = (id: string, user: string, tagDesktopId: string | null, name = id) =>
  toVideowallDesktop({
    id,
    name,
    status: 'Stopped',
    image: { id: 'img', type: 'stock', url: '' },
    user,
    user_name: user.toUpperCase(),
    tag_desktop_id: tagDesktopId
  } as UserDeploymentDesktop)

const DEPLOYMENT_DESKTOPS = [
  { tag_desktop_id: 'r1', name: 'Windows' },
  { tag_desktop_id: 'r2', name: 'Ubuntu' }
]

const desktops = [
  desktop('bob-ubuntu', 'bob', 'r2'),
  desktop('alice-ubuntu', 'alice', 'r2'),
  desktop('bob-windows', 'bob', 'r1'),
  desktop('alice-windows', 'alice', 'r1')
]

describe('groupVideowallDesktops', () => {
  it('lists users alphabetically with their desktops in deployment order', () => {
    const groups = groupVideowallDesktops(desktops, 'user', DEPLOYMENT_DESKTOPS)
    expect(groups.map((g) => g.label)).toEqual(['ALICE', 'BOB'])
    expect(groups[0].desktops.map((d) => d.id)).toEqual(['alice-windows', 'alice-ubuntu'])
  })

  it('lists desktops in deployment order, not by name', () => {
    const groups = groupVideowallDesktops(desktops, 'desktop', DEPLOYMENT_DESKTOPS)
    expect(groups.map((g) => g.label)).toEqual(['Windows', 'Ubuntu'])
    expect(groups[1].desktops.map((d) => d.id)).toEqual(['alice-ubuntu', 'bob-ubuntu'])
  })

  it('falls back to the desktop name when the deployment does not list it', () => {
    const groups = groupVideowallDesktops([desktop('x', 'carol', null, 'Legacy')], 'desktop', [])
    expect(groups).toEqual([expect.objectContaining({ label: 'Legacy' })])
  })
})

describe('toVideowallDesktop', () => {
  it('fills what the card requires and the deployment payload leaves out', () => {
    const d = desktop('a', 'alice', null)
    expect(d.type).toBe('persistent')
    expect(d.viewers).toEqual([])
    expect(d.interfaces).toEqual([])
  })
})

describe('isRunning', () => {
  it('counts a desktop still starting or shutting down as started', () => {
    expect(isRunning({ status: 'Starting' })).toBe(true)
    expect(isRunning({ status: 'Shutting-down' })).toBe(true)
    expect(isRunning({ status: 'Stopped' })).toBe(false)
  })
})

describe('videowallDesktopKey', () => {
  it('goes by the deployment desktop, or by name when the desktop has no tag', () => {
    expect(videowallDesktopKey(desktop('a', 'alice', 'r1'))).toBe('r1')
    expect(videowallDesktopKey(desktop('a', 'alice', null, 'Legacy'))).toBe('Legacy')
  })
})
