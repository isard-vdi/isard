import io from 'socket.io-client'
import { apiWebSockets } from '@/shared/constants'

export const socket = io(`${window.location.protocol}//${window.location.host}/userspace`,
  {
    path: apiWebSockets,
    transports: ['websocket'],
    autoConnect: false
  })
