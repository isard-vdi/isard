import { deploymentEventHandlers } from './deployment'
import { deploymentDesktopEventHandlers } from './deployment-desktop'
import { sharedDeploymentEventHandlers } from './shared-deployment'
import { desktopEventHandlers } from './desktop'
import { templateEventHandlers } from './template'
import { mediaEventHandlers } from './media'
import { recycleBinEventHandlers } from './recycle-bin'
import { bulkSpawnEventHandlers } from './bulk-spawn'
import { bookingEventHandlers } from './booking'
import { planningEventHandlers } from './planning'
import { usersEventHandlers } from './users'
import { messageEventHandlers } from './message'
import type { WsEventMap, WsEventName } from '@/types/ws-events'
import { QueryClient } from '@tanstack/vue-query'
import type { Socket } from 'socket.io-client'

type EventHandler<E extends WsEventName> = (queryClient: QueryClient, payload: string) => void

type EventHandlerMap = {
  [E in WsEventName]: EventHandler<E>
}

export const allEventHandlers: EventHandlerMap = {
  ...desktopEventHandlers,
  ...templateEventHandlers,
  ...deploymentEventHandlers,
  ...deploymentDesktopEventHandlers,
  ...sharedDeploymentEventHandlers,
  ...mediaEventHandlers,
  ...recycleBinEventHandlers,
  ...bulkSpawnEventHandlers,
  ...bookingEventHandlers,
  ...planningEventHandlers,
  ...usersEventHandlers,
  ...messageEventHandlers
}

export function registerSocketHandlers(socket: Socket, queryClient: QueryClient) {
  for (const [eventName, handler] of Object.entries(allEventHandlers)) {
    socket.on(eventName, (payload: string) => {
      handler(queryClient, payload)
    })
  }
}
