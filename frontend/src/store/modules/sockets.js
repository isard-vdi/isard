import { socket } from '@/utils/socket-instance'

export default {
  actions: {
    openSocket (context, { jwt, room }) {
      if (!socket.connected) {
        socket.io.opts.query = {
          jwt: jwt || localStorage.token,
          room
        }
        socket.open()
      }
    },
    closeSocket (context) {
      if (socket.connected) {
        socket.close()
      }
    }
  }
}
