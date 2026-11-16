<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useTemplateRef, type HTMLAttributes } from 'vue'
import Guacamole from '@isard/guacamole-common-js'
import type {
  Client,
  Display,
  InputSink,
  InputStream,
  Keyboard,
  Mouse,
  Status,
  Tunnel
} from 'guacamole-common-js'
import { GuacMouse } from '@/lib/guacamole/mouse'
import { createClipboard, type GuacamoleClipboard } from '@/lib/guacamole/clipboard'
import { cn } from '@/lib/utils'

export interface GuacamoleViewer {
  host: string
  vmHost: string
  vmUsername: string
  vmPassword: string
}

interface Props {
  viewer: GuacamoleViewer
  token: string
  class?: HTMLAttributes['class']
}

const { viewer, token, class: className } = defineProps<Props>()

const emit = defineEmits<{
  tunnelState: [state: Tunnel.State]
  clientState: [state: Client.State]
  tunnelError: [status: Status]
  clientError: [status: Status]
  ready: []
}>()

const viewport = useTemplateRef<HTMLElement>('viewport')
const screen = useTemplateRef<HTMLElement>('screen')
const connected = ref(false)

let tunnel: Tunnel | null = null
let client: Client | null = null
let display: Display | null = null
let inputSink: InputSink | null = null
let keyboard: Keyboard | null = null
let mouse: GuacMouse | null = null
let clipboard: GuacamoleClipboard | null = null
let resizeListening = false

let scale: number | null = null
let loggedIn = false
let resizing = false
const argumentValues: Record<string, string> = {}

const timers = new Set<ReturnType<typeof setTimeout>>()
const later = (fn: () => void, ms: number) => {
  const id = setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}

const tunnelUrl = () =>
  window.WebSocket
    ? `ws${location.protocol === 'https:' ? 's' : ''}://${viewer.host}/websocket-tunnel`
    : `${location.protocol}//${viewer.host}/tunnel`

const connectQuery = () => {
  const pixelDensity = window.devicePixelRatio || 1
  return new URLSearchParams({
    scheme: 'rdp',
    width: String(Math.floor(window.innerWidth * pixelDensity)),
    height: String(Math.floor(window.innerHeight * pixelDensity)),
    hostname: viewer.vmHost,
    'ignore-cert': 'true',
    session: token,
    username: viewer.vmUsername,
    password: viewer.vmPassword,
    'resize-method': 'display-update',
    'server-layout': 'es-es-qwerty',
    'enable-font-smoothing': 'true'
  }).toString()
}

const fitDisplay = () => {
  const elm = viewport.value
  if (!display || !elm || !elm.offsetWidth) return

  // guacd can report CONNECTED before the guest has sized the display: scaling against 0×0 blows it up.
  const width = display.getWidth()
  const height = display.getHeight()
  if (!width || !height) return

  const newScale = Math.min(elm.clientWidth / width, elm.clientHeight / height)
  // The scale only returns to 1 once the guest session has taken over the display.
  if (scale && scale !== 1 && scale !== newScale) {
    loggedIn = true
  }
  display.scale(newScale)
  scale = newScale
}

const resize = (mode?: 'mousemove') => {
  if (!client || !display) return
  if (mode === 'mousemove' && (loggedIn || resizing)) return

  const elm = viewport.value
  if (!elm || !elm.offsetWidth) return

  resizing = true

  const pixelDensity = window.devicePixelRatio || 1
  const width = elm.clientWidth * pixelDensity
  const height = elm.clientHeight * pixelDensity
  if (display.getWidth() !== width || display.getHeight() !== height) {
    client.sendSize(width, height)
  }

  // The display needs time to take the new size before it can be scaled to it.
  later(() => {
    fitDisplay()
    resizing = false
  }, 1000)
}

const onWindowResize = () => resize()
const onViewportMouseMove = () => resize('mousemove')

// Browsers keep guacamole's audio context suspended until a real user gesture.
const resumeAudio = () => {
  const context = Guacamole.AudioContextFactory.singleton
  if (context?.state === 'suspended') void context.resume()
}

const cursorFor = (hotspotX: number, hotspotY: number) => {
  switch (hotspotX) {
    case 11:
      return 'e-resize'
    case 4:
      return 's-resize'
    case 8:
      return hotspotY === 9 ? 'text' : 'crosshair'
    case 6:
      return 'pointer'
    default:
      return 'default'
  }
}

const sendMouseState = (state: Mouse.State) => {
  if (!client || !display) return
  const displayScale = display.getScale()
  client.sendMouseState(
    new Guacamole.Mouse.State(
      state.x / displayScale,
      state.y / displayScale,
      state.left,
      state.middle,
      state.right,
      state.up,
      state.down
    )
  )
}

const onArgv = (stream: InputStream, mimetype: string, name: string) => {
  if (mimetype !== 'text/plain' || !client) return

  const reader = new Guacamole.StringReader(stream)
  let value = ''
  reader.ontext = (text) => {
    value += text
  }
  reader.onend = () => {
    if (!client) return
    const valueStream = client.createArgumentValueStream('text/plain', name)
    valueStream.onack = (status) => {
      if (status.isError()) return
      argumentValues[name] = value
    }
  }
}

const onClientState = (state: Client.State) => {
  connected.value = state === Guacamole.Client.State.CONNECTED
  if (connected.value && client) {
    // Without this late resize the session never sizes itself to the page.
    later(() => resize(), 2000)
    if (!resizeListening) {
      window.addEventListener('resize', onWindowResize)
      viewport.value?.addEventListener('mousemove', onViewportMouseMove)
      resizeListening = true
    }
    clipboard?.setRemoteClipboard()
  }
  emit('clientState', state)
}

const onClientError = (status: Status) => {
  client?.disconnect()
  emit('clientError', status)
}

const onPageHide = () => client?.disconnect()

const connect = (screenElm: HTMLElement) => {
  tunnel = window.WebSocket
    ? new Guacamole.WebSocketTunnel(tunnelUrl())
    : new Guacamole.HTTPTunnel(tunnelUrl(), true)
  client = new Guacamole.Client(tunnel)

  document.addEventListener('click', resumeAudio)
  document.addEventListener('keydown', resumeAudio)

  clipboard = createClipboard(client)
  clipboard.install()

  tunnel.onerror = (status) => emit('tunnelError', status)
  tunnel.onstatechange = (state) => emit('tunnelState', state)

  client.onstatechange = onClientState
  client.onerror = onClientError
  client.onargv = onArgv
  client.onclipboard = clipboard.onClipboard

  display = client.getDisplay()
  // guacd reports CONNECTED before the guest has negotiated; only a sized display proves it did.
  display.onresize = (width, height) => {
    if (width > 0 && height > 0) {
      emit('ready')
      fitDisplay()
    }
  }
  display.oncursor = (_canvas, hotspotX, hotspotY) => {
    screenElm.style.cursor = cursorFor(hotspotX, hotspotY)
  }

  screenElm.appendChild(display.getElement())
  screenElm.addEventListener('contextmenu', (e) => {
    e.stopPropagation()
    e.preventDefault()
    e.returnValue = false
  })

  client.connect(connectQuery())
  window.addEventListener('pagehide', onPageHide)

  mouse = new GuacMouse(screenElm)
  display.showCursor(false)

  inputSink = new Guacamole.InputSink()
  screenElm.appendChild(inputSink.getElement())

  keyboard = new Guacamole.Keyboard(inputSink.getElement())
  keyboard.onkeydown = (keysym) => client?.sendKeyEvent(1, keysym)
  keyboard.onkeyup = (keysym) => client?.sendKeyEvent(0, keysym)
  inputSink.focus()

  mouse.onmouseup = mouse.onmousemove = sendMouseState
  mouse.onmousedown = (state) => {
    inputSink?.focus()
    sendMouseState(state)
  }

  later(() => {
    resize()
    inputSink?.focus()
  }, 1000)
}

onMounted(() => {
  if (screen.value) connect(screen.value)
})

// Our own teardown is not the connection failing: stop listening before closing.
onBeforeUnmount(() => {
  timers.forEach(clearTimeout)
  timers.clear()

  window.removeEventListener('pagehide', onPageHide)
  window.removeEventListener('resize', onWindowResize)
  viewport.value?.removeEventListener('mousemove', onViewportMouseMove)
  document.removeEventListener('click', resumeAudio)
  document.removeEventListener('keydown', resumeAudio)
  clipboard?.uninstall()

  if (keyboard) {
    keyboard.onkeydown = keyboard.onkeyup = null
    keyboard.reset()
  }
  if (mouse) {
    mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = null
  }
  if (tunnel) {
    tunnel.onerror = tunnel.onstatechange = null
  }
  if (client) {
    client.onstatechange = client.onerror = client.onargv = client.onclipboard = null
    client.disconnect()
  }

  tunnel = client = display = inputSink = keyboard = mouse = clipboard = null
})
</script>

<template>
  <div ref="viewport" :class="cn('size-full overflow-hidden', className)">
    <div v-show="connected" ref="screen" class="size-full overflow-hidden" tabindex="0" />
  </div>
</template>
