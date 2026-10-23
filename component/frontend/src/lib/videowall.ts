import {
  DesktopStatusEnum,
  DesktopTypeEnum,
  type ApiSchemasDomainsDesktopsUserDesktop,
  type UserDeploymentDesktop,
  type VideowallDeploymentDesktop
} from '@/gen/oas/apiv4'

import { desktopActionsData } from '@/lib/desktops'

export type VideowallDesktop = ApiSchemasDomainsDesktopsUserDesktop & {
  user_name: string
  user_photo: string
  tag_desktop_id: string | null
}

export type VideowallGroupBy = 'user' | 'desktop'

export interface VideowallGroup {
  key: string
  label: string
  photo?: string
  desktops: VideowallDesktop[]
}

// Same set the desktops view filters as started.
const RUNNING_STATUSES: string[] = [
  DesktopStatusEnum.STARTING,
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.SHUTTING_DOWN,
  DesktopStatusEnum.WAITING_IP
]

export const isRunning = (desktop: { status: string }) => RUNNING_STATUSES.includes(desktop.status)

/** Running, so its VNC console can be watched whatever viewers it offers, as in the old frontend. */
export const canViewInBrowser = (desktop: { status: string }) =>
  !!desktopActionsData(desktop.status).viewers

/** The deployment payload leaves optional what the desktop card requires. */
export function toVideowallDesktop(desktop: UserDeploymentDesktop): VideowallDesktop {
  return {
    ...desktop,
    type: desktop.type === DesktopTypeEnum.NONPERSISTENT ? 'nonpersistent' : 'persistent',
    viewers: desktop.viewers ?? [],
    user: desktop.user ?? '',
    user_name: desktop.user_name ?? '',
    user_photo: desktop.user_photo ?? '',
    group: desktop.group ?? '',
    category: desktop.category ?? '',
    interfaces: (desktop.interfaces ?? []) as VideowallDesktop['interfaces'],
    image: desktop.image as VideowallDesktop['image'],
    storage: desktop.storage as VideowallDesktop['storage'],
    progress: desktop.progress as VideowallDesktop['progress'],
    bastion_target: desktop.bastion_target as VideowallDesktop['bastion_target'],
    reservables: desktop.reservables as VideowallDesktop['reservables'],
    scheduled: desktop.scheduled as VideowallDesktop['scheduled'],
    tag_desktop_id: desktop.tag_desktop_id ?? null
  }
}

/** Which deployment desktop a desktop is; legacy ones without a tag go by name. */
export const videowallDesktopKey = (desktop: { tag_desktop_id: string | null; name: string }) =>
  desktop.tag_desktop_id ?? desktop.name

const byLabel = (a: { label: string }, b: { label: string }) =>
  a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })

/**
 * Users come out alphabetically, desktops in the order the deployment
 * defines them; inside a group the other dimension orders the cards.
 */
export function groupVideowallDesktops(
  desktops: VideowallDesktop[],
  groupBy: VideowallGroupBy,
  deploymentDesktops: VideowallDeploymentDesktop[]
): VideowallGroup[] {
  const order = new Map(deploymentDesktops.map((entry, index) => [entry.tag_desktop_id, index]))
  const desktopRank = (desktop: VideowallDesktop) =>
    order.get(desktop.tag_desktop_id) ?? deploymentDesktops.length

  const groups = new Map<string, VideowallGroup>()
  for (const desktop of desktops) {
    const key = groupBy === 'user' ? desktop.user : videowallDesktopKey(desktop)
    let group = groups.get(key)
    if (!group) {
      const entry = deploymentDesktops.find((e) => e.tag_desktop_id === desktop.tag_desktop_id)
      group =
        groupBy === 'user'
          ? { key, label: desktop.user_name, photo: desktop.user_photo, desktops: [] }
          : { key, label: entry?.name ?? desktop.name, desktops: [] }
      groups.set(key, group)
    }
    group.desktops.push(desktop)
  }

  const result = [...groups.values()]
  for (const group of result) {
    group.desktops.sort((a, b) =>
      groupBy === 'user'
        ? desktopRank(a) - desktopRank(b)
        : byLabel({ label: a.user_name }, { label: b.user_name })
    )
  }
  return groupBy === 'user'
    ? result.sort(byLabel)
    : result.sort((a, b) => desktopRank(a.desktops[0]) - desktopRank(b.desktops[0]))
}

/** What a group header sums up: anything neither running nor failed counts as stopped. */
export function countVideowallStatuses(desktops: { status: string }[]) {
  const started = desktops.filter(isRunning).length
  const failed = desktops.filter((d) => d.status === DesktopStatusEnum.FAILED).length
  return { started, stopped: desktops.length - started - failed, failed }
}
