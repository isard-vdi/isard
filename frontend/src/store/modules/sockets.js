import { socket } from '@/utils/socket-instance'

// socket.onAny((event, ...args) => {
//   console.log('onAny')
//   console.log(event, args)
// })
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
    localStorage.token = ''
    // window.location.href = '/login'
  } else {
    console.log('WS connection error: ' + err)
  }
})

export default {
  actions: {
    openSocket (context, { jwt, room }) {
      if (!socket.connected) {
        socket.io.opts.query = {
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
