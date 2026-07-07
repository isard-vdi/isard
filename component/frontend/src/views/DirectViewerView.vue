<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'
import { AlertModal } from '@/components/modal'

import {
  getDesktopViewerByTokenOptions,
  getDesktopViewerByTokenQueryKey,
  apiV4LoginConfigOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  resetDesktop as resetDesktopRequest,
  type DesktopDetailsResponse,
  type ViewersModel
} from '@/gen/oas/apiv4'
import { DesktopStatusEnum } from '@/gen/oas/apiv4/types.gen'
import { createClient, createConfig } from '@/gen/oas/apiv4/client'

import {
  desktopActionsData,
  desktopBookingNotificationText,
  DesktopActionsEnum
} from '@/lib/desktops'

import { useDirectViewerSocket } from '@/services/directViewerSocket'

import {
  DesktopCardBase,
  DesktopCardHeader,
  DesktopCardFooter,
  DesktopCardIp,
  DesktopCardNetworksOverlay
} from '@/components/desktop-card'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupSeparator } from '@/components/ui/button-group'
import { Icon } from '@/components/icon'
import { LoginNotification } from '@/components/login'
import { ChangeViewerModal } from '@/components/modal'
import { DesktopCardSkeleton } from '@/components/desktop-card'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import LogoSvg from '@/assets/logo.svg?url'
import Separator from '@/components/ui/separator/Separator.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'

const { t, d } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()
const cookies = vueuseCookies(['browser_viewer', 'viewerToken'])

// Path / sameSite are required so /viewer/noVNC/ can read both cookies; without path:/ the cookie is scoped to /direct/<token>.
const VIEWER_COOKIE_OPTS = { path: '/', sameSite: 'strict' } as const

const token = computed(() => route.params.token as string)

// Isolated apiv4 client for this view: uses the viewer JWT returned by
// get-viewer as its Authorization bearer. This deliberately bypasses the
// global apiv4 client's auth interceptor so that a user who is already
// logged in elsewhere keeps using their own JWT for other views.
const directViewerClient = createClient(createConfig())

const queryOptions = getDesktopViewerByTokenOptions({
  path: { token: token.value },
  client: directViewerClient
})

const {
  isPending,
  isError,
  error,
  data: desktopViewer
} = useQuery({
  ...queryOptions,
  enabled: !!token.value
})

const { data: loginConfig } = useQuery(apiV4LoginConfigOptions({ client: directViewerClient }))

const queryKey = getDesktopViewerByTokenQueryKey({
  path: { token: token.value }
})
const { isConnected, connect: connectSocket } = useDirectViewerSocket(token, queryClient, queryKey)

// Desktop details (hardware) are fetched separately so the user can
// see what they're about to launch while the viewer page is still
// booting. The endpoint lives on `direct_viewer_router` and needs the
// viewer JWT, so the query stays disabled until `directViewerClient`
// has its Authorization header set in the watch below.
const viewerJwt = ref<string | undefined>(undefined)
const { data: desktopDetails, isPending: isDetailsPending } = useQuery<DesktopDetailsResponse>({
  queryKey: ['direct-viewer-details', token],
  enabled: computed(() => !!viewerJwt.value),
  queryFn: async () => {
    const { data, error } = await directViewerClient.get<DesktopDetailsResponse>({
      url: `/api/v4/item/desktop/token/${encodeURIComponent(token.value)}/get-details`
    })
    if (error) throw error
    return data as DesktopDetailsResponse
  }
})

const hardwareBootOrder = computed(() => desktopDetails.value?.boot_order?.map((b) => b.name))
const hardwareVideos = computed(() => desktopDetails.value?.videos?.map((v) => v.name))
const hardwareIsos = computed(() => desktopDetails.value?.isos?.map((m) => m.name))
const hardwareFloppies = computed(() => desktopDetails.value?.floppies?.map((m) => m.name))
const hardwareInterfaces = computed(() => desktopDetails.value?.interfaces?.map((n) => n.name))
const hardwareDiskSize = computed(() => desktopDetails.value?.disks?.[0]?.size)
const hardwareVgpus = computed(() => desktopDetails.value?.reservables?.vgpus ?? null)
const hardwareViewers = computed(() => desktopDetails.value?.viewers ?? [])
const hardwareFullscreen = computed(() => desktopDetails.value?.fullscreen ?? false)
const hardwareCredentials = computed(() => ({
  username: desktopDetails.value?.credentials?.username ?? 'isard',
  password: desktopDetails.value?.credentials?.password ?? 'pirineus'
}))

watch(
  () => desktopViewer.value?.jwt,
  (jwt) => {
    directViewerClient.setConfig({
      headers: jwt ? { Authorization: `Bearer ${jwt}` } : undefined
    })
    viewerJwt.value = jwt
    if (jwt) {
      // noVNC reads `viewerToken` from document.cookie and uses it as the websocket security token (docker/static/noVNC/index.html: getCookie("viewerToken")). Without it the wss URL ends in `null` and websockify closes the connection.
      cookies.set('viewerToken', jwt, VIEWER_COOKIE_OPTS)
      if (!isConnected.value) {
        connectSocket(jwt)
      }
    }
  },
  { immediate: true }
)

const mainButtonData = computed(() => {
  if (!desktopViewer.value) return desktopActionsData(DesktopStatusEnum.UNKNOWN, false, true)
  return desktopActionsData(desktopViewer.value.status, false, true)
})

const normalizeViewerId = (viewerId: string) => viewerId.replace(/_/g, '-')

const viewerIds = computed<string[]>(() => {
  if (!desktopViewer.value?.viewers) return []
  const viewers = desktopViewer.value.viewers as Record<string, unknown>
  return Object.entries(viewers)
    .filter(([, value]) => value != null)
    .map(([key]) => normalizeViewerId(key))
})

const selectedViewerId = ref<string | undefined>(undefined)

const activeViewer = computed(() => {
  if (selectedViewerId.value && viewerIds.value.includes(selectedViewerId.value)) {
    return selectedViewerId.value
  }
  return viewerIds.value[0] ?? null
})

const activeViewerLabel = computed(() => {
  if (!activeViewer.value) return ''
  return t(`viewers.${activeViewer.value}`)
})

watch(
  viewerIds,
  (ids) => {
    if (!selectedViewerId.value && ids.length > 0) {
      selectedViewerId.value = ids[0]
    }
  },
  { immediate: true }
)

// The card is rendered whenever `desktopViewer` exists, across every
// status (started, stopped, failed, etc.) so the user always has an
// action button and is never stranded when the owner stops the desktop
// from elsewhere. The footer's `mainButtonData` drives what action is
// shown per status.

const isWaitingIp = computed(() => desktopViewer.value?.status === DesktopStatusEnum.WAITING_IP)

const viewerNeedsIp = (viewerId: string) => viewerId.includes('rdp')

const isViewerLoading = (viewerId: string) => isWaitingIp.value && viewerNeedsIp(viewerId)

const activeViewerLoading = computed(() =>
  activeViewer.value ? isViewerLoading(activeViewer.value) : false
)

const notificationText = computed<string | null>(() => {
  if (!desktopViewer.value) return null

  const dv = desktopViewer.value

  const bookingText = desktopBookingNotificationText(dv, t, d)
  if (bookingText) return bookingText

  if (
    [DesktopStatusEnum.STARTED, DesktopStatusEnum.WAITING_IP, DesktopStatusEnum.STARTING].includes(
      dv.status
    ) &&
    dv.scheduled?.shutdown
  ) {
    const shutdownDate = new Date(dv.scheduled.shutdown)
    return t('components.desktops.desktop-card.notification-bar.shutdown', {
      date: d(shutdownDate, { dateStyle: 'short' }),
      time: d(shutdownDate, { timeStyle: 'short' })
    })
  }

  return null
})

const showNetworkOverlay = ref(false)
const isViewerChangeModalOpen = ref(false)

const logoSrc = ref('/custom/logo.svg')
const handleLogoError = () => {
  logoSrc.value = LogoSvg
}

const showResetModal = ref(false)

const { mutate: resetDesktop, isPending: isResetting } = useMutation({
  mutationFn: async () => {
    const { data, error } = await resetDesktopRequest({
      path: { token: token.value },
      client: directViewerClient
    })
    if (error) throw error
    return data
  },
  onSuccess: () => {
    showResetModal.value = false
  }
})

// Start desktop (authenticated via the direct-viewer JWT). Used for
// explicit user clicks after the owner has stopped the desktop from
// elsewhere; initial auto-start is handled server-side by get-viewer.
const { mutate: startDesktop } = useMutation({
  mutationFn: async () => {
    const { data, error } = await directViewerClient.put<{ id: string }>({
      url: `/api/v4/item/desktop/token/${encodeURIComponent(token.value)}/start-desktop`
    })
    if (error) throw error
    return data
  }
})

const handleDesktopAction = (action: DesktopActionsEnum) => {
  switch (action) {
    case DesktopActionsEnum.Reset:
    case DesktopActionsEnum.Stop:
      showResetModal.value = true
      break
    case DesktopActionsEnum.Start:
      startDesktop()
      break
    default:
      break
  }
}

const openViewer = (viewerId: string) => {
  if (!desktopViewer.value?.viewers) return
  const viewers = desktopViewer.value.viewers as Record<string, any>
  const viewer = viewers[viewerId] ?? viewers[viewerId.replace(/-/g, '_')]
  if (!viewer) return

  if (viewer.kind === 'browser') {
    if (viewer.cookie) {
      cookies.set('browser_viewer', viewer.cookie, VIEWER_COOKIE_OPTS)
    }
    if (viewer.viewer) {
      // `direct=1` flips noVNC's cookie precedence to `viewerToken` (no session cookie exists in the direct-viewer flow).
      const url = new URL(viewer.viewer, window.location.origin)
      url.searchParams.set('direct', '1')
      window.open(url.toString(), '_blank')
    }
  } else if (viewer.kind === 'file' && viewer.name && viewer.ext && viewer.mime && viewer.content) {
    downloadFile(viewer.name, viewer.ext, viewer.mime, viewer.content)
  }
}

const downloadFile = (name: string, ext: string, mime: string, content: string) => {
  const el = document.createElement('a')
  el.setAttribute('href', `data:${mime};charset=utf-8,${encodeURIComponent(content || '')}`)
  el.setAttribute('download', `${name}.${ext}`)
  el.style.display = 'none'
  document.body.appendChild(el)
  el.click()
  document.body.removeChild(el)
}
</script>

<template>
  <div class="flex flex-col min-h-screen bg-base-background relative z-0 overflow-hidden">
    <header class="flex items-center justify-between px-8 py-5 border-b border-gray-warm-200">
      <h1 class="text-display-xs font-semibold text-gray-warm-900">
        {{ t('views.direct-viewer.title') }}
      </h1>
      <img :src="logoSrc" alt="IsardVDI logo" class="h-[40px]" @error="handleLogoError" />
    </header>
    <main class="flex-1 flex flex-col items-center justify-center px-2">
      <div class="w-full grid place-items-center">
        <template v-if="isPending">
          <div class="flex flex-col">
            <div class="flex flex-col gap-2.5 items-center animate-pulse">
              <div class="h-5 w-48 rounded-md bg-gray-warm-200"></div>
              <div class="h-9 w-72 rounded-md bg-gray-warm-200"></div>
            </div>
            <Separator class="pt-4 pb-5" />
            <div class="flex gap-10 items-start">
              <div>
                <DesktopCardSkeleton variant="started" class="shadow-md h-[310px] w-[433px]" />
              </div>
              <div class="flex flex-col gap-10 max-w-[700px]">
                <section
                  class="p-5 rounded-md border border-gray-warm-200 shadow-md flex flex-col gap-7"
                >
                  <div>
                    <div class="flex items-center gap-3 mb-3.5">
                      <div class="w-1.5 h-4 rounded-full bg-brand-700"></div>
                      <h3 class="text-lg font-semibold text-gray-warm-900 leading-0">
                        {{ t('views.direct-viewer.access-summary') }}
                      </h3>
                    </div>
                    <DomainAccessSummary
                      :loading="true"
                      :credentials="{ username: '', password: '' }"
                      :fullscreen="false"
                      :viewers="[]"
                    />
                  </div>
                  <Separator />
                  <div>
                    <div class="flex items-center gap-3 mb-3.5">
                      <div class="w-1.5 h-4 rounded-full bg-brand-700"></div>
                      <h3 class="text-lg font-semibold text-gray-warm-900 leading-0">
                        {{ t('views.direct-viewer.hardware-summary') }}
                      </h3>
                    </div>
                    <DomainHardwareSummary :loading="true" />
                  </div>
                </section>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="isError">
          <div
            class="flex flex-col items-center gap-3 rounded-lg p-8 border border-error-300 bg-error-25"
          >
            <Icon name="alert-circle" stroke-color="error-600" size="lg" />
            <template v-if="error?.description_code === 'desktop_not_booked'">
              <h2 class="text-lg font-semibold text-error-700">
                {{ t('views.direct-viewer.errors.not-booked.title') }}
              </h2>
              <p class="text-sm text-error-600 text-center whitespace-pre-line">
                {{ t('views.direct-viewer.errors.not-booked.description') }}
              </p>
            </template>
            <template v-else>
              <h2 class="text-lg font-semibold text-error-700">
                {{ t('views.direct-viewer.error-title') }}
              </h2>
              <p class="text-sm text-error-600 text-center">
                {{ t('views.direct-viewer.error-description') }}
              </p>
            </template>
          </div>
        </template>
        <template v-else-if="desktopViewer">
          <div class="flex flex-col">
            <div class="flex flex-col gap-1.5 items-center">
              <p class="text-display-sm text-left font-light text-brand-700">
                {{ t('views.direct-viewer.connecting-to') }}
              </p>
              <h2 class="text-display-md text-left font-semibold text-brand-700">
                {{ desktopViewer.name }}
              </h2>
            </div>
            <Separator class="pt-4 pb-5" />
            <div class="flex gap-10 items-start">
              <div>
                <LoginNotification
                  v-if="loginConfig?.notification_cover?.enabled"
                  :config="loginConfig.notification_cover"
                />
                <div class="self-center">
                  <DesktopCardBase
                    desktop-kind="nonpersistent"
                    :image-url="desktopViewer.image?.url ?? ''"
                    :show-overlay="showNetworkOverlay"
                    class="shadow-md"
                  >
                    <template #header-actions>
                      <Button
                        hierarchy="link-gray"
                        size="sm"
                        class="w-9! h-9! flex align-center justify-center bg-base-black/30 hover:bg-base-black/50 p-0! backdrop-blur-[4px]"
                        icon="modem-02"
                        icon-stroke-color="base-white"
                        @click="showNetworkOverlay = !showNetworkOverlay"
                      />
                    </template>
                    <template #ip>
                      <DesktopCardIp :desktop-status="desktopViewer.status" :desktop-ip="null" />
                    </template>
                    <template #overlay>
                      <div class="z-10 pl-[40px] pr-3 pb-2">
                        <DesktopCardNetworksOverlay
                          :desktop-id="desktopViewer.id"
                          :direct-viewer-token="token"
                          :direct-viewer-client="directViewerClient"
                          :full-height="
                            !(notificationText && desktopViewer.description?.trim().length !== 0)
                          "
                        />
                      </div>
                    </template>
                    <template #header>
                      <DesktopCardHeader
                        :notification-text="notificationText"
                        :name="desktopViewer.name"
                        :description="desktopViewer.description || ''"
                      />
                    </template>
                    <template #footer>
                      <DesktopCardFooter
                        :main-button-data="mainButtonData"
                        :desktop-status="desktopViewer.status"
                        :desktop-viewers="[]"
                        :desktop-ip="null"
                        :preferred-viewer="selectedViewerId"
                        @main-button-click="
                          handleDesktopAction(mainButtonData.actionButton!.action)
                        "
                      />
                      <ButtonGroup v-if="viewerIds.length > 0" class="ml-auto min-w-0">
                        <Button
                          class="min-w-0 overflow-hidden"
                          :icon="activeViewerLoading ? 'loading-02' : ''"
                          :icon-class="
                            activeViewerLoading
                              ? 'motion-safe:animate-[spin_2s_linear_infinite]'
                              : ''
                          "
                          :disabled="activeViewerLoading"
                          @click="openViewer(activeViewer!)"
                        >
                          <span class="min-w-0 truncate">{{ activeViewerLabel }}</span>
                        </Button>
                        <template v-if="viewerIds.length > 1">
                          <ButtonGroupSeparator color="brand-800" />
                          <Button
                            icon="settings-02"
                            class="rounded-l-none"
                            :aria-label="t('views.direct-viewer.select-viewer')"
                            @click="isViewerChangeModalOpen = true"
                          />
                        </template>
                      </ButtonGroup>
                    </template>
                  </DesktopCardBase>
                </div>
              </div>
              <div class="flex flex-col gap-10 max-w-[700px]">
                <section
                  class="bg-gray-warm-50 p-5 rounded-md border border-gray-warm-200 shadow-md flex flex-col gap-7"
                >
                  <div>
                    <div class="flex items-center gap-3 mb-3.5">
                      <div class="w-1.5 h-4 rounded-full bg-brand-700 self-stretch"></div>
                      <h3 class="text-lg font-semibold text-gray-warm-900 leading-0">
                        {{ t('views.direct-viewer.access-summary') }}
                      </h3>
                    </div>
                    <DomainAccessSummary
                      :credentials="hardwareCredentials"
                      :fullscreen="hardwareFullscreen"
                      :viewers="hardwareViewers"
                      :loading="isDetailsPending"
                    />
                  </div>
                  <Separator />
                  <div>
                    <div class="flex items-center gap-3 mb-3.5">
                      <div class="w-1.5 h-4 rounded-full bg-brand-700 self-stretch"></div>
                      <h3 class="text-lg font-semibold text-gray-warm-900 leading-0">
                        {{ t('views.direct-viewer.hardware-summary') }}
                      </h3>
                    </div>
                    <DomainHardwareSummary
                      :vcpu="desktopDetails?.vcpu"
                      :memory="desktopDetails?.memory"
                      :disk-bus="desktopDetails?.disk_bus"
                      :disk-size="hardwareDiskSize"
                      :boot-order="hardwareBootOrder"
                      :videos="hardwareVideos"
                      :isos="hardwareIsos"
                      :floppies="hardwareFloppies"
                      :vgpus="hardwareVgpus"
                      :interfaces="hardwareInterfaces"
                      :loading="isDetailsPending"
                    />
                  </div>
                </section>
              </div>
            </div>
          </div>
        </template>
      </div>
    </main>
    <ChangeViewerModal
      :open="isViewerChangeModalOpen"
      :available-viewer-ids="viewerIds"
      :current-viewer-id="activeViewer ?? ''"
      @close="isViewerChangeModalOpen = false"
      @change="(id) => (selectedViewerId = id)"
    />
    <img
      src="@/assets/img/mountains.svg"
      class="fixed bottom-0 right-0 -z-10 select-none pointer-events-none"
    />
    <img
      src="@/assets/img/clouds.svg"
      class="absolute hidden lg:block top-20 lg:left-0 xl:left-10 -z-10 select-none pointer-events-none"
    />

    <AlertModal
      :open="showResetModal"
      @update:open="showResetModal = $event"
      level="warning"
      size="lg"
      :title="t('views.direct-viewer.reset-modal.title')"
      :description="t('views.direct-viewer.reset-modal.description')"
      :loading="isResetting"
    >
      <template #footer>
        <Button
          hierarchy="secondary-gray"
          size="lg"
          :disabled="isResetting"
          @click="showResetModal = false"
        >
          {{ t('views.direct-viewer.reset-modal.cancel') }}
        </Button>
        <Button hierarchy="primary" size="lg" :disabled="isResetting" @click="resetDesktop()">
          {{ t('views.direct-viewer.reset-modal.confirm') }}
        </Button>
      </template>
    </AlertModal>
  </div>
</template>
