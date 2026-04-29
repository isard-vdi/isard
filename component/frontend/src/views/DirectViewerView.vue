<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { io, type Socket } from 'socket.io-client'
import { useCookies } from '@vueuse/integrations/useCookies'
import {
  getDesktopViewerByTokenOptions,
  getDesktopViewerByTokenQueryKey,
  getViewerDocsOptions,
  apiV4LoginConfigOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DesktopStatusEnum, type DesktopViewerResponse, type ErrorResponse } from '@/gen/oas/apiv4'
import { webSockets } from '@/lib/constants'
import { formatAsTime, utcToLocalTime } from '@/lib/booking/date-utils'
import {
  DirectViewerButton,
  DirectViewerHelpRDP,
  DirectViewerHelpSpice,
  DirectViewerResetModal,
  DirectViewerSkeleton
} from '@/components/direct-viewer'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

const { t, locale } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()
const cookies = useCookies(['viewerToken'])

const token = computed(() => {
  const param = route.params.token
  return Array.isArray(param) ? param[0] : (param ?? '')
})

const showResetModal = ref(false)
const helpModal = ref<'spice' | 'rdp' | null>(null)

const viewerQueryOptions = computed(() =>
  getDesktopViewerByTokenOptions({
    path: { token: token.value }
  })
)
const viewerQueryKey = computed(() =>
  getDesktopViewerByTokenQueryKey({
    path: { token: token.value }
  })
)
const {
  data: viewerData,
  error: viewerError,
  isPending: viewerPending
} = useQuery({
  ...viewerQueryOptions.value,
  queryKey: viewerQueryKey,
  enabled: computed(() => !!token.value),
  retry: false
})

const { data: viewerDocs } = useQuery(getViewerDocsOptions())
const { data: loginConfig } = useQuery(apiV4LoginConfigOptions())

const errorMessage = computed(() => {
  if (!viewerError.value) return null
  const err = viewerError.value as ErrorResponse | undefined
  if (err?.description_code === 'desktop_not_booked_until' && err.params?.start) {
    const localStart = utcToLocalTime(err.params.start as string)
    return t('views.direct-viewer.errors.desktop_not_booked_until', { start: localStart })
  }
  if (err?.description_code) {
    return t(`views.direct-viewer.errors.${err.description_code}`, err.params ?? {})
  }
  return t('views.direct-viewer.errors.not_found')
})

const viewersList = computed(() => {
  const viewers = viewerData.value?.viewers ?? {}
  return Object.values(viewers).filter((v): v is NonNullable<typeof v> => Boolean(v))
})

const browserViewers = computed(() => viewersList.value.filter((v) => v.kind === 'browser'))
const fileViewers = computed(() => viewersList.value.filter((v) => v.kind === 'file'))

const viewerDescriptions = computed(
  () =>
    ({
      vnc: t('views.direct-viewer.description.vnc'),
      rdp: t('views.direct-viewer.description.rdp'),
      spice: t('views.direct-viewer.description.spice'),
      rdpgw: t('views.direct-viewer.description.rdpgw')
    }) as Record<string, string>
)

const shutdownText = computed(() => {
  const scheduled = viewerData.value?.scheduled
  if (!scheduled?.shutdown || !viewerData.value?.name) return ''
  return t('components.message-modal.messages.desktop-time-limit', {
    name: viewerData.value.name,
    date: formatAsTime(utcToLocalTime(scheduled.shutdown as string))
  })
})

const isWaiting = computed(() => viewerData.value?.status === DesktopStatusEnum.WAITING_IP)

let socket: Socket | null = null

function openSocket(jwt: string, room: string) {
  closeSocket()
  socket = io('/userspace', {
    path: webSockets,
    auth: (cb) => cb({ jwt }),
    query: { room },
    transports: ['websocket'],
    rememberUpgrade: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 2000,
    randomizationFactor: 0.5,
    timeout: 3000
  })
  socket.on('directviewer_update', (payload: string) => {
    try {
      const next = JSON.parse(payload) as DesktopViewerResponse
      queryClient.setQueryData(viewerQueryKey.value, next)
    } catch (err) {
      console.warn('[direct-viewer] invalid payload:', err)
    }
  })
  socket.connect()
}

function closeSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}

function autoLaunchIfApplicable(data: DesktopViewerResponse) {
  if (viewersList.value.length !== 1) return
  const only = viewersList.value[0]
  if (
    only.kind === 'browser' &&
    (only.protocol === 'vnc' ||
      (only.protocol === 'rdp' && data.status !== DesktopStatusEnum.WAITING_IP))
  ) {
    triggerOpen.value = only
  }
}

const triggerOpen = ref<unknown>(null)

watch(viewerData, (data, prev) => {
  if (!data || prev) return
  cookies.set('viewerToken', data.jwt, { path: '/', sameSite: 'strict' })
  openSocket(data.jwt, data.id)
  autoLaunchIfApplicable(data)
})

watch(isWaiting, (next, prev) => {
  if (prev === true && next === false) {
    const data = viewerData.value
    if (
      data &&
      viewersList.value.length === 1 &&
      viewersList.value[0].kind === 'browser' &&
      viewersList.value[0].protocol === 'rdp'
    ) {
      triggerOpen.value = viewersList.value[0]
    }
  }
})

onMounted(() => {
  document.title = t('views.direct-viewer.title')
})

onUnmounted(() => {
  closeSocket()
})

const tokenStr = computed(() => token.value)
const _ = locale
</script>

<template>
  <div class="min-h-screen w-full bg-gray-warm-400 py-6">
    <div class="max-w-5xl mx-auto px-2 md:px-8">
      <Alert v-if="loginConfig?.notification_cover?.enabled" class="bg-white border-error-600 mb-4">
        <AlertTitle v-if="loginConfig.notification_cover.title">
          {{ loginConfig.notification_cover.title }}
        </AlertTitle>
        <AlertDescription>
          {{ loginConfig.notification_cover.description }}
        </AlertDescription>
      </Alert>

      <div
        class="rounded-t-[30px] flex justify-center items-center"
        style="background: #3a4445; height: 100px"
      >
        <div
          class="rounded-full bg-white overflow-hidden flex items-center justify-center"
          style="height: 110px; width: 110px; margin-top: 45px; z-index: 5"
        >
          <img
            :src="'/api/v4/logo'"
            :alt="t('views.direct-viewer.logo-alt')"
            class="max-w-full max-h-full"
          />
        </div>
      </div>

      <div class="rounded-b-[30px] bg-gray-warm-100 px-4 pt-12 pb-8">
        <div v-if="viewerError" class="text-center">
          <Alert class="bg-white border-error-600 mb-4">
            <AlertDescription>{{ errorMessage }}</AlertDescription>
          </Alert>
        </div>

        <template v-else>
          <div class="flex justify-end mb-2">
            <Button
              v-if="!viewerPending && viewerData"
              hierarchy="destructive"
              size="sm"
              class="gap-2"
              @click="showResetModal = true"
            >
              <Icon name="refresh-cw-05" stroke-color="base-white" size="sm" />
              {{ t('views.direct-viewer.restart') }}
            </Button>
          </div>

          <div class="text-center mb-6">
            <h5 class="font-bold text-gray-warm-600 mb-2">
              {{ t('views.direct-viewer.title') }}
            </h5>
            <div
              v-if="!viewerData?.name && !viewerError"
              class="flex items-center justify-center gap-2"
            >
              <h2 class="text-2xl font-bold">{{ t('views.direct-viewer.loading') }}</h2>
              <Spinner size="sm" color="green" />
            </div>
            <h1 v-else class="text-3xl font-bold">{{ viewerData?.name }}</h1>
            <h4 v-if="shutdownText" class="text-gray-warm-600 mt-2">{{ shutdownText }}</h4>
            <h5 v-if="viewerData?.description" class="text-gray-warm-600 mt-1">
              {{ viewerData.description }}
            </h5>
          </div>

          <div class="flex flex-row flex-wrap justify-center pt-2">
            <template v-if="viewerPending">
              <DirectViewerSkeleton />
              <DirectViewerSkeleton />
            </template>
            <template v-else>
              <div
                v-if="browserViewers.length"
                class="flex-1 min-w-[280px] max-w-md text-center px-2"
              >
                <h6 class="font-bold text-gray-warm-600 mb-2">
                  {{ t('views.direct-viewer.browser.title') }}
                </h6>
                <div class="h-[75px] flex items-center justify-center text-sm text-gray-warm-500">
                  <p>{{ t('views.direct-viewer.browser.subtitle') }}</p>
                </div>
                <DirectViewerButton
                  v-for="viewer in browserViewers"
                  :key="`${viewer.kind}-${viewer.protocol}`"
                  :viewer="viewer"
                  :state="viewerData?.status ?? ''"
                  :description="viewerDescriptions[viewer.protocol]"
                  :token="tokenStr"
                  @help="(p) => (helpModal = p === 'spice' ? 'spice' : 'rdp')"
                />
              </div>

              <div v-if="fileViewers.length" class="flex-1 min-w-[280px] max-w-md text-center px-2">
                <h6 class="font-bold text-gray-warm-600 mb-2">
                  {{ t('views.direct-viewer.file.title') }}
                </h6>
                <div class="h-[75px] flex items-center justify-center text-sm text-gray-warm-500">
                  <p>{{ t('views.direct-viewer.file.subtitle') }}</p>
                </div>
                <DirectViewerButton
                  v-for="viewer in fileViewers"
                  :key="`${viewer.kind}-${viewer.protocol}`"
                  :viewer="viewer"
                  :state="viewerData?.status ?? ''"
                  :description="viewerDescriptions[viewer.protocol]"
                  :token="tokenStr"
                  @help="(p) => (helpModal = p === 'spice' ? 'spice' : 'rdp')"
                />
              </div>
            </template>
          </div>
        </template>

        <div class="text-center mt-8">
          <a
            href="https://www.isardvdi.com/"
            target="_blank"
            rel="noopener noreferrer"
            class="text-gray-warm-600 hover:text-gray-warm-700"
          >
            <i18n-t keypath="views.direct-viewer.powered-by" tag="p">
              <template #isardvdi><strong>IsardVDI</strong></template>
            </i18n-t>
          </a>
        </div>
      </div>
    </div>

    <DirectViewerResetModal
      :open="showResetModal"
      :token="tokenStr"
      @close="showResetModal = false"
    />
    <DirectViewerHelpSpice
      :open="helpModal === 'spice'"
      :documentation-url="viewerDocs?.viewers_documentation_url ?? ''"
      @close="helpModal = null"
    />
    <DirectViewerHelpRDP
      :open="helpModal === 'rdp'"
      :documentation-url="viewerDocs?.viewers_documentation_url ?? ''"
      @close="helpModal = null"
    />
  </div>
</template>
