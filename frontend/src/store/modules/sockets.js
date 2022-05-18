import { socket } from '@/utils/socket-instance'

export default {
  actions: {
    openSocket (context, { room, deploymentId }) {
      socket.io.opts.query = {
        jwt: sessionStorage.token,
        room,
        deploymentId
      }
      socket.open()
    },
    closeSocket (context) {
      if (socket.connected) {
        socket.close()
      }
    }
  }
}
