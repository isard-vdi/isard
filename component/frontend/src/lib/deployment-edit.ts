import { DesktopStatusEnum, type DeploymentResponse } from '@/gen/oas/apiv4'

// Mirrors Deployment.check_desktops_started: any other status rejects the edit.
const EDITABLE_STATUSES: string[] = [
  DesktopStatusEnum.STOPPED,
  DesktopStatusEnum.FAILED,
  DesktopStatusEnum.UNKNOWN
]

/** The desktops that keep a deployment from being edited. */
export function startedDesktopCount(deployment?: DeploymentResponse): number {
  return (deployment?.users ?? [])
    .flatMap((user) => user.desktops ?? [])
    .filter((desktop) => !!desktop.status && !EDITABLE_STATUSES.includes(desktop.status)).length
}
