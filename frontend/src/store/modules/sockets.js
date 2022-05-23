import { socket } from '@/utils/socket-instance'

export default {
  actions: {
    openSocket (context, { room, deploymentId, jwt }) {
      socket.io.opts.query = {
        jwt: jwt || sessionStorage.token,
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
