<template>
  <div
    ref="viewport"
    class="viewport-rdp"
  >
    <modal
      v-show="clientState!==3"
      ref="modal"
    />
    <!-- trick AudioContext to think the user has clicked in order to be able to start the viewer -->
    <p
      ref="connectionbutton"
      style="margin-bottom: 0.1px;"
      @click="startViewer()"
    />
    <!-- tabindex allows for div to be focused -->
    <div
      v-show="clientState===3"
      ref="display"
      class="display-rdp"
      tabindex="0"
    />
  </div>
</template>

<script>
import Guacamole from 'guacamole-common-js'
import GuacMouse from '@/lib/GuacMouse'
import states from '@/lib/states'
import clipboard from '@/lib/clipboard'
import Modal from '@/components/Modal'
import * as cookies from 'tiny-cookie'
import { jwtDecode } from 'jwt-decode'

Guacamole.Mouse = GuacMouse.mouse

export default {
  name: 'Rdp',
  components: {
    Modal
  },
  data () {
    return {
      connected: false,
      display: null,
      resizing: false,
      currentAdjustedHeight: null,
      client: null,
      keyboard: null,
      mouse: null,
      lastEvent: null,
      connectionState: states.IDLE,
      errorMessage: '',
      arguments: {},
      scale: null,
      loggedIn: false,
      host: '',
      desktopIp: '',
      clientState: 0
    }
  },
  watch: {
    connectionState (state) {
      this.$refs.modal.show(state, this.errorMessage)
    }
  },
  mounted () {
    this.$refs.connectionbutton.click()
  },
  methods: {
    startViewer () {
      let cookie = ''
      const queryString = window.location.search
      const urlParams = new URLSearchParams(queryString)
      let urlCookie = ''
      let jwt = ''
      if (urlParams.length > 1) {
        urlCookie = urlParams.get('cookie').replace('%3D', '=')
        jwt = urlParams.get('jwt').replace('%3D', '=')
      }
      if (jwt.length > 1 && urlCookie.length > 1) {
        cookie = urlCookie
        localStorage.viewerToken = jwt
      } else {
        cookie = cookies.getCookie('browser_viewer')
      }
      if (!cookie) {
        this.connectionState = states.COOKIE_ERROR
        return
      }
      const params = jwtDecode(cookie).web_viewer
      if (new Date() > new Date(params.exp * 1000)) {
        this.connectionState = states.COOKIE_EXPIRED
        return
      }
      this.host = params.host
      this.desktopIp = params.vmHost
      this.username = params.vmUsername
      this.password = params.vmPassword

      const queryParams = {
        scheme: 'rdp',
        hostname: this.desktopIp,
        'ignore-cert': true,
        session: localStorage.viewerToken,
        username: this.username,
        password: this.password,
        'resize-method': 'display-update',
        'server-layout': 'es-es-qwerty',
        'enable-font-smoothing': true
      }

      let query = ''
      for (const [name, param] of Object.entries(queryParams)) {
        query += `${name}=${param}&`
      }
      query = query.slice(0, -1)

      this.connected = true

      this.connect(query)
    },
    getWsUrl () {
      return `ws${location.protocol === 'https:' ? 's' : ''}://${this.host}/websocket-tunnel`
    },
    getHtmlUrl () {
      return `${location.protocol}//${this.host}/tunnel`
    },
    send (cmd) {
      if (!this.client) {
        return
      }
      for (const c of cmd.data) {
        this.client.sendKeyEvent(1, c.charCodeAt(0))
      }
    },
    copy (cmd) {
      if (!this.client) {
        return
      }
      clipboard.cache = {
        type: 'text/plain',
        data: cmd.data
      }
      clipboard.setRemoteClipboard(this.client)
    },
    handleMouseState (mouseState) {
      const scaledMouseState = Object.assign({}, mouseState, {
        x: mouseState.x / this.display.getScale(),
        y: mouseState.y / this.display.getScale()
      })
      this.client.sendMouseState(scaledMouseState)
    },
    resizeOnMove () {
      this.resize('mousemove')
    },
    resize (mode) {
      if (mode === 'mousemove' && (this.loggedIn || this.resizing)) {
        return
      }

      this.resizing = true

      const elm = this.$refs.viewport
      if (!elm || !elm.offsetWidth) {
        // resize is being called on the hidden window
        return
      }

      const pixelDensity = window.devicePixelRatio || 1
      const width = elm.clientWidth * pixelDensity
      const height = elm.clientHeight * pixelDensity
      if (
        this.display.getWidth() !== width ||
        this.display.getHeight() !== height
      ) {
        this.client.sendSize(width, height)
      }
      // setting timeout so display has time to get the correct size
      setTimeout(() => {
        const newScale = Math.min(
          elm.clientWidth / Math.max(this.display.getWidth(), 1),
          elm.clientHeight / Math.max(this.display.getHeight(), 1)
        )

        if (this.scale && this.scale !== 1 && this.scale !== newScale) { // Has logged in if scale returns to 1
          this.loggedIn = true
        }

        this.display.scale(newScale)
        this.scale = newScale
        this.resizing = false
      }, 1000)
    },
    connect (query) {
      let tunnel

      if (window.WebSocket && !this.forceHttp) {
        tunnel = new Guacamole.WebSocketTunnel(this.getWsUrl())
      } else {
        tunnel = new Guacamole.HTTPTunnel(this.getHtmlUrl, true)
      }

      if (this.client) {
        this.display.scale(0)
        this.uninstallKeyboard()
      }

      this.client = new Guacamole.Client(tunnel)
      clipboard.install(this.client)

      tunnel.onerror = (status) => {
        // eslint-disable-next-line no-console
        console.error(`Tunnel failed ${JSON.stringify(status)}`)
        this.connectionState = states.TUNNEL_ERROR
      }

      tunnel.onstatechange = (state) => {
        switch (state) {
          // Connection is being established
          case Guacamole.Tunnel.State.CONNECTING:
            this.connectionState = states.CONNECTING
            break

          // Connection is established / no longer unstable
          case Guacamole.Tunnel.State.OPEN:
            this.connectionState = states.CONNECTED
            break

          // Connection is established but misbehaving
          case Guacamole.Tunnel.State.UNSTABLE:
            // TODO
            break

          // Connection has closed
          case Guacamole.Tunnel.State.CLOSED:
            this.connectionState = states.DISCONNECTED
            break
        }
      }

      this.client.onstatechange = (clientState) => {
        this.clientState = clientState
        switch (clientState) {
          case 0:
            this.connectionState = states.IDLE
            break
          case 1:
            this.connectionState = states.WAITING
            break
          case 2:
            this.connectionState = states.WAITING
            break
          case 3:
            this.connectionState = states.CONNECTED
            // without this manual resize, the viewer is never going to "start" correctly. Maybe 2000ms isn't enough for all the situations?
            setTimeout(() => this.resize(), 2000)
            window.addEventListener('resize', this.resize)

            this.$refs.viewport.addEventListener('mousemove', this.resizeOnMove)

            clipboard.setRemoteClipboard(this.client)

          // eslint-disable-next-line no-fallthrough
          case 4:
          case 5:
            // disconnected, disconnecting
            this.connectionState = states.DISCONNECTED
            break
        }
      }

      this.client.onerror = (error) => {
        this.client.disconnect()
        // eslint-disable-next-line no-console
        console.error(`Client error ${JSON.stringify(error)}`)
        this.errorMessage = error.message
        this.connectionState = states.CLIENT_ERROR
        this.clientState = -1
      }

      this.client.onsync = () => {}

      // Test for argument mutability whenever an argument value is received
      this.client.onargv = (stream, mimetype, name) => {
        if (mimetype !== 'text/plain') return

        const reader = new Guacamole.StringReader(stream)

        // Assemble received data into a single string
        let value = ''
        reader.ontext = (text) => {
          value += text
        }

        // Test mutability once stream is finished, storing the current value for the argument only if it is mutable
        reader.onend = () => {
          const stream = this.client.createArgumentValueStream(
            'text/plain',
            name
          )
          stream.onack = (status) => {
            if (status.isError()) {
              // ignore reject
              return
            }
            this.arguments[name] = value
          }
        }
      }

      this.client.onclipboard = clipboard.onClipboard
      this.display = this.client.getDisplay()
      const displayElm = this.$refs.display
      displayElm.appendChild(this.display.getElement())
      displayElm.addEventListener('contextmenu', (e) => {
        e.stopPropagation()
        if (e.preventDefault) {
          e.preventDefault()
        }
        e.returnValue = false
      })

      this.display.oncursor = (_, code, subCode) => {
        const cursorStyle = displayElm.style

        switch (code) {
          case 0:
            cursorStyle.cursor = 'default'
            break
          case 11:
            cursorStyle.cursor = 'e-resize'
            break
          case 4:
            cursorStyle.cursor = 's-resize'
            break
          case 8:
            cursorStyle.cursor = subCode === 9 ? 'text' : 'crosshair'
            break
          case 6:
            cursorStyle.cursor = 'pointer'
            break
          case 3:
            cursorStyle.cursor = 'default'
            break
          default:
            cursorStyle.cursor = 'default'
        }
      }

      this.client.connect(query)
      window.onunload = () => {
        this.client.disconnect()
        localStorage.viewerToken = ''
      }

      this.mouse = new Guacamole.Mouse(displayElm)

      // Change to test in Oracle to hide software cursor
      this.display.showCursor(false)

      // allows focusing on the display div so that keyboard doesn't always go to session
      displayElm.onclick = () => {
        displayElm.focus()
      }
      displayElm.onfocus = () => {
        displayElm.className = 'focus'
      }
      displayElm.onblur = () => {
        displayElm.className = ''
      }

      this.keyboard = new Guacamole.Keyboard(displayElm)
      this.installKeyboard()
      this.mouse.onmousedown = this.mouse.onmouseup = this.mouse.onmousemove = this.handleMouseState
      setTimeout(() => {
        this.resize()
        displayElm.focus()
      }, 1000) // $nextTick wasn't enough
    },
    installKeyboard () {
      this.keyboard.onkeydown = (keysym) => {
        this.client.sendKeyEvent(1, keysym)
      }
      this.keyboard.onkeyup = (keysym) => {
        this.client.sendKeyEvent(0, keysym)
      }
    },
    uninstallKeyboard () {
      this.keyboard.onkeydown = this.keyboard.onkeyup = () => {}
    }
  }
}
</script>

<style scoped>
.display-rdp {
  overflow: hidden;
  width: 100%;
  height: 100%;
}

.viewport-rdp {
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
