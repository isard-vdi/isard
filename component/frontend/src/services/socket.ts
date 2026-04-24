import { io } from 'socket.io-client'
import { webSockets } from '@/lib/constants'
import { useAuthStore } from '@/stores/auth'

export function createSocket() {
  return io(`/userspace`, {
    path: webSockets,
    // socket.io-client v4 accepts `auth` as a function that's invoked on
    // every (re)connect handshake. Resolve the token from the auth store at
    // call time so the infinite reconnection loop picks up tokens refreshed
    // mid-session by renewSession(), instead of replaying an expired JWT
    // captured at socket-construction time forever.
    auth: (cb) => cb({ jwt: useAuthStore().token ?? '' }),
    transports: ['websocket'],
    rememberUpgrade: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 2000,
    randomizationFactor: 0.5,
    timeout: 3000
  })
}
