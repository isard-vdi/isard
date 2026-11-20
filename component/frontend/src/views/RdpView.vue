<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute } from 'vue-router'
import { useCookies } from '@vueuse/integrations/useCookies'
import { useQueryClient } from '@tanstack/vue-query'
import { jwtDecode } from 'jwt-decode'
import GuacamoleCommon from '@isard/guacamole-common-js'
import type { Client, Status, Tunnel } from 'guacamole-common-js'
import { userOwnsDesktop } from '@/gen/oas/apiv4'
import { createClient, createConfig } from '@/gen/oas/apiv4/client'
import { Guacamole, GuacamoleStatus, type GuacamoleViewer } from '@/components/guacamole'
import { DesktopTimeoutModal } from '@/components/modal'
import { RdpConnectionState } from '@/lib/guacamole/states'
import { clearViewerToken, setViewerToken } from '@/lib/viewers'
import { createSocket } from '@/services/socket'
import { messageEventHandlers } from '@/stores/ws-handlers/message'

interface BrowserViewerClaims {
  web_viewer: GuacamoleViewer & { exp: number; vmName?: string }
}

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 5000

const { Client: GuacClient, Tunnel: GuacTunnel, Status: GuacStatus } = GuacamoleCommon

const route = useRoute()
const cookies = useCookies(['browser_viewer', 'viewerToken'])
const queryClient = useQueryClient()

// The viewer token is not the login session: the global client would swap it for the session
// token, and send a 403 to the error page.
const viewerClient = createClient(createConfig())

let socket: ReturnType<typeof createSocket> | null = null

const connectionState = ref(RdpConnectionState.IDLE)
const clientState = ref<Client.State>(GuacClient.State.IDLE)
const retries = ref(0)
const attempt = ref(0)
const viewer = shallowRef<GuacamoleViewer | null>(null)
const token = ref('')
const desktopName = ref<string>()

let lastError: Status | null = null
let retryTimer: ReturnType<typeof setTimeout> | undefined

const showStatus = computed(() => clientState.value !== GuacClient.State.CONNECTED)

// A direct viewer token only reaches its own desktop: it gets the stop warnings but cannot extend.
const directViewer = computed(() => {
  try {
    return !!jwtDecode<{ data?: { desktop_id?: string } }>(token.value).data?.desktop_id
  } catch {
    return false
  }
})

// guacd reports a failed security negotiation with the same code; only its message tells them apart.
const isAuthFailure = (error: Status | null) =>
  !!error &&
  error.code === GuacStatus.Code.CLIENT_UNAUTHORIZED &&
  /authentication failure/i.test(error.message || '')

const queryParam = (name: string) => {
  const value = route.query[name]
  return typeof value === 'string' && value.length > 1 ? value : undefined
}

const decodeBrowserViewer = (cookie: string) => {
  try {
    return jwtDecode<BrowserViewerClaims>(cookie).web_viewer
  } catch {
    return undefined
  }
}

const startViewer = () => {
  const urlCookie = queryParam('cookie')
  const urlJwt = queryParam('jwt')
  let browserViewer: string | undefined
  let viewerToken: string | undefined
  if (urlCookie && urlJwt) {
    setViewerToken(cookies, urlJwt)
    browserViewer = urlCookie
    viewerToken = urlJwt
  } else {
    browserViewer = cookies.get('browser_viewer')
    viewerToken = cookies.get('viewerToken')
  }

  if (!browserViewer) {
    connectionState.value = RdpConnectionState.COOKIE_ERROR
    return
  }
  if (!viewerToken) {
    connectionState.value = RdpConnectionState.VIEWER_TOKEN_ERROR
    return
  }

  const params = decodeBrowserViewer(browserViewer)
  if (!params) {
    connectionState.value = RdpConnectionState.COOKIE_ERROR
    return
  }
  desktopName.value = params.vmName
  if (Date.now() > params.exp * 1000) {
    connectionState.value = RdpConnectionState.COOKIE_EXPIRED
    return
  }

  viewer.value = {
    host: params.host,
    vmHost: params.vmHost,
    vmUsername: params.vmUsername,
    vmPassword: params.vmPassword
  }
  token.value = viewerToken
  viewerClient.setConfig({ headers: { Authorization: `Bearer ${viewerToken}` } })
  clientState.value = GuacClient.State.IDLE
  attempt.value++

  // A login token joins its user's room and a direct viewer token its desktop's room: the scheduler
  // sends the stop warnings to both.
  if (!socket) {
    socket = createSocket(() => token.value)
    socket.on('msg', (payload: string) => messageEventHandlers.msg(queryClient, payload))
  }
}

// The same check guac runs before opening the tunnel: the API denies a desktop that is not
// running (403 for a login token, 428 for a direct viewer token).
const isDesktopStopped = async () => {
  try {
    const { response } = await userOwnsDesktop({
      client: viewerClient,
      body: { ip: viewer.value?.vmHost }
    })
    return [403, 428].includes(response?.status ?? 0)
  } catch {
    return false
  }
}

const scheduleRetry = () => {
  // The client and the tunnel may both report the same failure.
  if (retryTimer) return

  if (retries.value < MAX_RETRIES) {
    retries.value++
    connectionState.value = RdpConnectionState.RETRYING
    console.info(`Connection error. Retrying connection in ${RETRY_DELAY_MS / 1000} seconds...`)
    retryTimer = setTimeout(async () => {
      // Checked on retry: right after a stop the desktop may still be shutting down.
      const stopped = await isDesktopStopped()
      retryTimer = undefined
      if (stopped) {
        console.info('Desktop stopped. Not retrying.')
        connectionState.value = RdpConnectionState.DESKTOP_STOPPED
        return
      }
      startViewer()
    }, RETRY_DELAY_MS)
  } else {
    console.info('Max number of retries reached. Disconnecting.')
    connectionState.value = isAuthFailure(lastError)
      ? RdpConnectionState.RDP_AUTH_FAILED
      : RdpConnectionState.RDP_NOT_RUNNING
  }
}

const onTunnelState = (state: Tunnel.State) => {
  switch (state) {
    case GuacTunnel.State.CONNECTING:
      connectionState.value =
        retries.value > 0 ? RdpConnectionState.RETRYING : RdpConnectionState.CONNECTING
      break
    case GuacTunnel.State.OPEN:
      connectionState.value = RdpConnectionState.CONNECTED
      break
    case GuacTunnel.State.CLOSED:
      // The tunnel closes right after reporting its error: keep showing the pending retry.
      if (retryTimer) break
      connectionState.value = RdpConnectionState.DISCONNECTED
      break
  }
}

const onClientState = (state: Client.State) => {
  clientState.value = state
  switch (state) {
    case GuacClient.State.IDLE:
      connectionState.value = RdpConnectionState.IDLE
      break
    case GuacClient.State.CONNECTING:
    case GuacClient.State.WAITING:
      connectionState.value = RdpConnectionState.WAITING
      break
    case GuacClient.State.CONNECTED:
      connectionState.value = RdpConnectionState.CONNECTED
      break
    case GuacClient.State.DISCONNECTING:
    case GuacClient.State.DISCONNECTED:
      connectionState.value = RdpConnectionState.DISCONNECTED
      break
  }
}

const onTunnelError = (status: Status) => {
  console.error(`Tunnel failed ${JSON.stringify(status)}`)
  scheduleRetry()
}

const onClientError = (status: Status) => {
  lastError = status
  console.error(`Client error ${JSON.stringify(status)}`)
  scheduleRetry()
}

const onReady = () => {
  retries.value = 0
  lastError = null
}

const onPageHide = () => {
  clearTimeout(retryTimer)
  clearViewerToken(cookies)
}

const reload = () => window.location.reload()

onMounted(() => {
  window.addEventListener('pagehide', onPageHide)
  startViewer()
})

onBeforeUnmount(() => {
  window.removeEventListener('pagehide', onPageHide)
  clearTimeout(retryTimer)
  socket?.disconnect()
  socket = null
})
</script>

<template>
  <div class="h-dvh w-screen overflow-hidden bg-gray-warm-800">
    <Guacamole
      v-if="viewer"
      :key="attempt"
      :viewer="viewer"
      :token="token"
      @tunnel-state="onTunnelState"
      @client-state="onClientState"
      @tunnel-error="onTunnelError"
      @client-error="onClientError"
      @ready="onReady"
    />
    <GuacamoleStatus
      v-show="showStatus"
      :state="connectionState"
      :retry="retries"
      :max-retries="MAX_RETRIES"
      :desktop-name="desktopName"
      @reload="reload"
    />
    <DesktopTimeoutModal :client="viewerClient" :extendable="!directViewer" />
  </div>
</template>
