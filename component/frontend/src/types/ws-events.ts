/**
 * WebSocket event payload types.
 *
 * These types describe the JSON payloads emitted by the v3 API's
 * RethinkDB changefeed threads (api/src/api/libv2/api_socketio_*.py).
 * They are NOT the same shape as the v4 API Pydantic models — the v3
 * backend applies its own parsing/mapping before emitting.
 *
 * All payloads arrive as JSON strings and must be JSON.parse()'d first.
 */

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

/** Minimal payload used for delete events */
export interface WsDeletePayload {
  id: string
}

// ---------------------------------------------------------------------------
// Desktops — emitted by DomainsThread via _parse_desktop()
// ---------------------------------------------------------------------------

export interface WsDesktopProgress {
  percentage: number | null
  throughput_average: number | null
  time_left: number | null
  size: number | null
}

export interface WsDesktopScheduled {
  shutdown: boolean
}

export interface WsDesktopPayload {
  id: string
  name: string
  state: string
  type: 'persistent' | 'nonpersistent'
  template: string | null
  viewers: string[]
  icon: string
  image: Record<string, unknown> | null
  description: string
  ip: string | null
  progress: WsDesktopProgress | null
  editable: boolean
  scheduled: WsDesktopScheduled
  server: boolean | null
  accessed: number | null
  tag: string | null
  visible: boolean | null
  user: string
  user_name: string | null
  group: string
  group_name: string | null
  category: string
  category_name: string | null
  reservables: Record<string, string[]> | null
  interfaces: { id: string; mac?: string }[]
  current_action: string | null
  storage: (string | null)[]
  permissions: string[]
  needs_booking: boolean
  next_booking_start: string | null
  next_booking_end: string | null
  booking_id: string | false
}

// ---------------------------------------------------------------------------
// Desktops queue — emitted by apiv4 AdminNotifyService.notify_desktop_queue
// when a hypervisor reports queued desktop operations. Payload is a map of
// desktop_id → entry, where the entry's `position` is the user-visible queue
// position. See component/apiv4/src/api/services/admin_notify.py:34-61.
// ---------------------------------------------------------------------------

export interface WsDesktopsQueueEntry {
  desktop_id?: string
  position: number
  [key: string]: unknown
}

export type WsDesktopsQueuePayload = Record<string, WsDesktopsQueueEntry>

// ---------------------------------------------------------------------------
// Templates — emitted by DomainsThread (same _parse_desktop for
// /userspace, raw DB doc for /administrators)
// ---------------------------------------------------------------------------

/** Template payload on /userspace — same shape as desktop (kind != desktop) */
export type WsTemplatePayload = WsDesktopPayload

// ---------------------------------------------------------------------------
// Deployments — emitted by DeploymentsThread
// ---------------------------------------------------------------------------

export interface WsDeploymentPayload {
  id: string
  name: string
  user: string
  co_owners: string[]
  visible: boolean
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Deployment desktops — emitted by DesktopDomainHandler when a desktop
// belonging to a deployment (tag) changes. Payload is the result of
// DeploymentDesktopsProcessed._parse_deployment_desktop: a parsed desktop
// (same shape as WsDesktopPayload) enriched with deployment-scoped fields.
// ---------------------------------------------------------------------------

export interface WsDeploymentDesktopPayload extends WsDesktopPayload {
  viewer: Record<string, unknown> | false
  user_photo?: string | null
  group_name?: string | null
}

// ---------------------------------------------------------------------------
// Media — emitted by MediaThread
// ---------------------------------------------------------------------------

export interface WsMediaProgress {
  received: number
  total: number
  speed: number
  speed_download_average: number
  received_percent?: number
  time_left?: string
}

export interface WsMediaPayload {
  id: string
  name: string
  description: string
  user: string
  category: string
  status: string
  kind: string
  progress: WsMediaProgress
  editable?: boolean
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Recycle Bin — emitted by RecycleBin class
// ---------------------------------------------------------------------------

/** add_recycle_bin: full entry with item counts */
export interface WsRecycleBinAddPayload {
  id: string
  desktops: number
  templates: number
  storages: number
  deployments: number
  categories: number
  groups: number
  users: number
  items_in_bin?: number
  [key: string]: unknown
}

/** update_recycle_bin / delete_recycle_bin: minimal status update */
export interface WsRecycleBinUpdatePayload {
  id: string
  status: string
}

// ---------------------------------------------------------------------------
// Bulk-spawn — emitted by Desktops.new_from_templateTh while a deployment's
// desktops are being created; brackets a long-running spawn so the UI can
// disable the deployment's "Recreate" action until the loop ends.
// ---------------------------------------------------------------------------

export interface WsBulkSpawnPayload {
  deployment_id: string
}

// ---------------------------------------------------------------------------
// Bookings / Plans — emitted by change-handler BookingsHandler /
// ResourcePlannerHandler.
// ---------------------------------------------------------------------------

export interface WsBookingPayload {
  id: string
  user_id: string
  item_id: string
  item_type: 'desktop' | 'deployment'
  title: string
  start: string
  end: string
  event_type: string
  editable: boolean
  [key: string]: unknown
}

export interface WsPlanPayload {
  id: string
  user_id: string
  item_id: string
  item_type: string
  subitem_id: string
  start: string
  end: string
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Users — emitted by change-handler UsersHandler to /userspace room=user.id
// when the user's own record changes (e.g. email verified). Payload is the
// full user model. See component/change-handler/src/handlers/users.py.
// ---------------------------------------------------------------------------

export interface WsUserDataPayload {
  id: string
  email?: string | null
  email_verified?: number | boolean | null
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Shared-deployment desktop start/stop — emitted by DesktopDomainHandler
// when a participant desktop in a shared deployment crosses the started
// boundary. Payload is the deployment id (i.e. desktop.tag).
// See component/change-handler/src/handlers/domains.py:405-415.
// ---------------------------------------------------------------------------

export interface WsSharedDeploymentDesktopPayload {
  id: string
}

// ---------------------------------------------------------------------------
// Event name → payload type mapping
// ---------------------------------------------------------------------------

export interface WsEventMap {
  desktop_add: WsDesktopPayload
  desktop_update: WsDesktopPayload
  desktop_delete: WsDeletePayload
  desktops_queue: WsDesktopsQueuePayload

  template_add: WsTemplatePayload
  template_update: WsTemplatePayload
  template_delete: WsDeletePayload

  deployment_add: WsDeploymentPayload
  deployment_update: WsDeploymentPayload
  deployment_delete: WsDeletePayload

  deploymentdesktop_add: WsDeploymentDesktopPayload
  deploymentdesktop_update: WsDeploymentDesktopPayload
  deploymentdesktop_delete: WsDeletePayload
  deployments_update: WsDeploymentPayload

  media_add: WsMediaPayload
  media_update: WsMediaPayload
  media_delete: WsDeletePayload

  add_recycle_bin: WsRecycleBinAddPayload
  update_recycle_bin: WsRecycleBinUpdatePayload
  delete_recycle_bin: WsRecycleBinUpdatePayload

  creating_desktops: WsBulkSpawnPayload
  end_creating_desktops: WsBulkSpawnPayload

  booking_add: WsBookingPayload
  booking_update: WsBookingPayload
  booking_delete: WsDeletePayload

  plan_add: WsPlanPayload
  plan_update: WsPlanPayload
  plan_delete: WsPlanPayload

  users_data: WsUserDataPayload
  users_delete: WsDeletePayload

  shared_deployment_desktop_start: WsSharedDeploymentDesktopPayload
  shared_deployment_desktop_stop: WsSharedDeploymentDesktopPayload
}

export type WsEventName = keyof WsEventMap
