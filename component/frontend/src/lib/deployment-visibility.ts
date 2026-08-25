import type { DeploymentDesktop, DeploymentUserDetail } from '@/gen/oas/apiv4'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import type { VisibilityState } from '@/components/deployments/visibility'

/** One (user, desktop) cell of the visibility matrix. */
export interface MatrixDesktop {
  desktop_id: string
  tag_desktop_id?: string | null
  visible: boolean
  status?: string | null
}

const DESKTOP_COL_PREFIX = 'desktop:'

export interface DesktopColumn {
  key: string
  tagDesktopId: string | null
  name: string
}

/** Column axis of the matrix: one entry per desktop of the deployment. */
export function desktopColumns(desktops: DeploymentDesktop[]): DesktopColumn[] {
  return desktops.map((desktop, index) => ({
    key: `${DESKTOP_COL_PREFIX}${desktop.tag_desktop_id ?? `legacy-${index}`}`,
    tagDesktopId: desktop.tag_desktop_id ?? null,
    name: desktop.name
  }))
}

export const userDesktops = (user: DeploymentUserDetail): MatrixDesktop[] =>
  (user.desktops ?? []) as MatrixDesktop[]

export const cellFor = (user: DeploymentUserDetail, tagDesktopId: string | null) =>
  userDesktops(user).find((desktop) => (desktop.tag_desktop_id ?? null) === tagDesktopId)

/** true / false / 'indeterminate' over a set of cells. */
export function aggregate(desktops: MatrixDesktop[]): VisibilityState {
  if (!desktops.length) return false
  const visible = desktops.filter((desktop) => desktop.visible).length
  if (visible === 0) return false
  return visible === desktops.length ? true : 'indeterminate'
}

export const rowState = (user: DeploymentUserDetail): VisibilityState =>
  aggregate(userDesktops(user))

/** Cells of one desktop across every user — the column aggregate. */
export function columnCells(
  users: DeploymentUserDetail[],
  tagDesktopId: string | null
): MatrixDesktop[] {
  return users
    .map((user) => cellFor(user, tagDesktopId))
    .filter((desktop): desktop is MatrixDesktop => !!desktop)
}

export const columnState = (
  users: DeploymentUserDetail[],
  tagDesktopId: string | null
): VisibilityState => aggregate(columnCells(users, tagDesktopId))

/**
 * Derived from the matrix rather than `tag_visible`, which only says whether
 * *any* desktop is visible and so cannot express "mixed".
 */
export function deploymentState(users: DeploymentUserDetail[], fallback: boolean): VisibilityState {
  const cells = users.flatMap(userDesktops)
  if (!cells.length) return fallback
  return aggregate(cells)
}

export const visibleCount = (desktops: MatrixDesktop[]): number =>
  desktops.filter((desktop) => desktop.visible).length

// The statuses the API stops when a hide asks for it, so what the modal
// counts is exactly what the server would interrupt.
const RUNNING_STATES: string[] = [
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.STARTING,
  DesktopStatusEnum.STARTING_PAUSED,
  DesktopStatusEnum.SHUTTING_DOWN
]

export const isRunning = (desktop?: MatrixDesktop): boolean =>
  !!desktop?.status && RUNNING_STATES.includes(desktop.status)

/** Hiding these is the change a user would notice mid-session. */
export const runningCount = (desktops: MatrixDesktop[]): number => desktops.filter(isRunning).length

/**
 * Same tri-state for surfaces that carry only the totals rather than the
 * per-desktop matrix, so the deployments list and the visibility page agree.
 */
export function visibilityStateFromCounts(
  visible: number,
  total: number,
  fallback: boolean
): VisibilityState {
  if (!total) return fallback
  if (visible === 0) return false
  return visible === total ? true : 'indeterminate'
}
