import { socket } from '@/utils/socket-instance'
import store from '@/store/index.js'
import { sessionCookieName } from '@/shared/constants'
import { getCookie } from 'tiny-cookie'

export default {
  actions: {
    openSocket (context, { jwt, room }) {
      if (!socket.connected || jwt) {
        const sessionCookie = getCookie(sessionCookieName)
        socket.auth.jwt = jwt || sessionCookie
        socket.io.opts.query = {
          room
        }
        socket.open()
        socket.on('connect', function () {
          console.log('WS connected')
        })
        socket.on('connect_error', (err) => {
          if (err.message === 'timeout') {
            console.log('WS connection timeout')
          } else if (err.message === 'websocket error') {
            console.log('WS connection error')
          } else if (err.message === 'Connection rejected by server') {
            console.log('WS connection not authorized')
            store.dispatch('logout')
          } else {
            console.log('WS connection error: ' + err)
          }
        })
      }
    },
    closeSocket (context) {
      if (socket.connected) {
        socket.off('connect')
        socket.off('connect_error')
        socket.close()
      }
    }
  }
}
