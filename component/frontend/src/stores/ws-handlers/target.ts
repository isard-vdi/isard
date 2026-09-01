import type { WsDeletePayload, WsTargetPayload } from '@/types/ws-events'
import type {
  ApiSchemasDomainsDesktopsUserDesktop as UserDesktop,
  DesktopBastionResponse,
  UserDesktopBastionTarget
} from '@/gen/oas/apiv4'
import { QueryClient } from '@tanstack/vue-query'
import {
  getUserDesktopsOptions,
  getDesktopBastionLegacyOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const desktopsListKey = getUserDesktopsOptions().queryKey

function toBastionTarget(target: WsTargetPayload): UserDesktopBastionTarget {
  return {
    id: target.id,
    http: target.http,
    ssh: target.ssh,
    domains: target.domains ?? []
  }
}

function patchBastionTarget(
  queryClient: QueryClient,
  matches: (desktop: UserDesktop) => boolean,
  bastionTarget: UserDesktopBastionTarget | null
) {
  queryClient.setQueryData(desktopsListKey, (old) => {
    if (!old?.desktops) return old
    if (!old.desktops.some(matches)) return old
    return {
      ...old,
      desktops: old.desktops.map((desktop) =>
        matches(desktop) ? { ...desktop, bastion_target: bastionTarget } : desktop
      )
    }
  })
}

function patchDesktopBastion(queryClient: QueryClient, target: WsTargetPayload) {
  const key = getDesktopBastionLegacyOptions({
    path: { desktop_id: target.desktop_id }
  }).queryKey
  queryClient.setQueryData(key, (old) =>
    old
      ? {
          ...old,
          id: target.id,
          user_id: target.user_id,
          desktop_id: target.desktop_id,
          http: target.http,
          ssh: target.ssh,
          domains: target.domains ?? []
        }
      : undefined
  )
}

export const targetEventHandlers = {
  targets_add: (queryClient: QueryClient, payload: string) => {
    const data: WsTargetPayload = JSON.parse(payload)
    patchBastionTarget(queryClient, (d) => d.id === data.desktop_id, toBastionTarget(data))
    patchDesktopBastion(queryClient, data)
  },

  targets_update: (queryClient: QueryClient, payload: string) => {
    const data: WsTargetPayload = JSON.parse(payload)
    patchBastionTarget(queryClient, (d) => d.id === data.desktop_id, toBastionTarget(data))
    patchDesktopBastion(queryClient, data)
  },

  targets_delete: (queryClient: QueryClient, payload: string) => {
    const data: WsDeletePayload = JSON.parse(payload)
    patchBastionTarget(queryClient, (d) => d.bastion_target?.id === data.id, null)
    queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey[0] as { _id?: string } | undefined
        if (key?._id !== 'getDesktopBastionLegacy') return false
        return (query.state.data as DesktopBastionResponse | undefined)?.id === data.id
      }
    })
  }
}
