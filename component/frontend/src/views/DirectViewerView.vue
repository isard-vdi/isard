<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'
import { AlertModal } from '@/components/modal'
import { DomainInfoModal } from '@/components/desktops'

import {
  getDesktopViewerByTokenOptions,
  getDesktopViewerByTokenQueryKey,
  getDesktopDetailsFromTokenOptions,
  startDesktopFromTokenMutation,
  resetDesktopMutation,
  apiV4LoginConfigOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  renewDesktopViewerByToken,
  type DesktopViewerResponse,
  type ViewersModel,
  type BrowserVncValues
} from '@/gen/oas/apiv4'
import { DesktopStatusEnum } from '@/gen/oas/apiv4/types.gen'
import { createClient, createConfig } from '@/gen/oas/apiv4/client'

import {
  desktopActionsData,
  desktopBookingNotificationText,
  DesktopActionsEnum
} from '@/lib/desktops'

import { withOptimisticStatus } from '@/lib/optimistic'

import { useDirectViewerSocket } from '@/services/directViewerSocket'
import { useJwtRenewal } from '@/composables/useJwtRenewal'

import {
  DesktopCardBase,
  DesktopCardHeader,
  DesktopCardFooter,
  DesktopCardIp,
  DesktopCardNetworksOverlay,
  DesktopCardBastionOverlay,
  DesktopCardOverlayButton,
  DesktopCardInfoOverlay,
  cardOverlayPaddingVariants,
  cardOverlayLabelVariants
} from '@/components/desktop-card'
import type { CardSize } from '@/components/desktop-card'
import DirectViewerCardPreview from '@/components/desktop-card/parts/DirectViewerCardPreview.vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupSeparator } from '@/components/ui/button-group'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Icon } from '@/components/icon'
import { LoginNotification } from '@/components/login'
import { ChangeViewerModal } from '@/components/modal'
import { DesktopBastionInfoModal, DesktopNetworksModal } from '@/components/desktops'
import { DesktopCardSkeleton } from '@/components/desktop-card'
import LogoSvg from '@/assets/logo.svg?url'

const { t, d } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()
const cookies = vueuseCookies(['browser_viewer', 'viewerToken'])

// Path / sameSite are required so /viewer/noVNC/ can read both cookies; without path:/ the cookie is scoped to /direct/<token>.
const VIEWER_COOKIE_OPTS = { path: '/', sameSite: 'strict' } as const

const CARD_SIZE: CardSize = 'xl'

const networksOverlayRef = ref<InstanceType<typeof DesktopCardNetworksOverlay> | null>(null)

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

type OverlayKind = 'networks' | 'bastion' | 'info'
const activeOverlay = ref<OverlayKind | null>(null)

const toggleOverlay = (kind: OverlayKind) => {
  activeOverlay.value = activeOverlay.value === kind ? null : kind
}

const showBastionModal = ref(false)
const showNetworksModal = ref(false)
const showDesktopInfoModal = ref(false)

const viewerJwt = ref<string | undefined>(undefined)
const { data: desktopDetails } = useQuery({
  ...getDesktopDetailsFromTokenOptions({
    path: { token: token.value },
    client: directViewerClient
  }),
  enabled: computed(() => !!viewerJwt.value && showDesktopInfoModal.value)
})

const bastion = computed(() => desktopViewer.value?.bastion)
const desktopIp = computed(() => desktopViewer.value?.ip)

// The viewer JWT lasts 30 minutes and every direct-viewer request carries it,
// so a page left open would 401 until a reload. get-viewer can't be polled to
// refresh it — it starts a stopped desktop and logs an access — hence the
// dedicated renew-viewer route.
const { mutateAsync: renewViewerToken } = useMutation({
  mutationFn: () =>
    renewDesktopViewerByToken({
      path: { token: token.value },
      client: directViewerClient,
      throwOnError: true
    }),
  onSuccess: ({ data }) => {
    queryClient.setQueryData(queryKey, (old: DesktopViewerResponse | undefined) =>
      // `status` on this payload is synthesised by the viewer helper — always
      // Started/WaitingIP, because get-viewer is normally called right after a
      // start. A renewal doesn't start anything, so keep the live status the
      // socket maintains instead of flipping a stopped desktop back to Started.
      old ? { ...old, ...data, status: old.status } : data
    )
  }
})

useJwtRenewal(viewerJwt, renewViewerToken)

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
        connectSocket(() => viewerJwt.value)
      }
    }
  },
  { immediate: true }
)

const mainButtonData = computed(() => {
  if (!desktopViewer.value) return desktopActionsData(DesktopStatusEnum.UNKNOWN, false, true)
  return desktopActionsData(desktopViewer.value.status, false, true)
})

const desktopCardKind = computed(() => desktopViewer.value?.type as 'persistent' | 'nonpersistent')

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

const vncValues = computed<BrowserVncValues | null>(() => {
  const viewers = desktopViewer.value?.viewers as Record<string, any> | undefined
  if (!viewers) return null
  const vnc = viewers['browser-vnc'] ?? viewers['browser_vnc']
  return vnc?.values ?? null
})

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

const isViewerChangeModalOpen = ref(false)

const logoSrc = ref('/custom/logo.svg')
const handleLogoError = () => {
  logoSrc.value = LogoSvg
}

const showResetModal = ref(false)

// Both direct-viewer mutations are addressed by the share token, not a desktop id.
interface DirectViewerVars {
  path: { token: string }
}
const directViewerVars = computed<DirectViewerVars>(() => ({ path: { token: token.value } }))

const { mutate: resetDesktop, isPending: isResetting } = useMutation(
  withOptimisticStatus<DesktopViewerResponse, DirectViewerVars>({
    queryClient,
    queryKey,
    nextStatus: DesktopStatusEnum.RESETTING,
    // Mirror DesktopEvents.desktop_reset: any other state is rejected server-side.
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STARTED ||
      current === DesktopStatusEnum.SHUTTING_DOWN ||
      current === DesktopStatusEnum.SUSPENDED ||
      current === DesktopStatusEnum.STOPPING,
    baseMutation: resetDesktopMutation({ client: directViewerClient }),
    onSuccess: () => {
      showResetModal.value = false
    }
  })
)

// Start desktop (authenticated via the direct-viewer JWT). Used for
// explicit user clicks after the owner has stopped the desktop from
// elsewhere; initial auto-start is handled server-side by get-viewer.
const { mutate: startDesktop } = useMutation(
  withOptimisticStatus<DesktopViewerResponse, DirectViewerVars>({
    queryClient,
    queryKey,
    nextStatus: DesktopStatusEnum.STARTING,
    // Mirror DesktopDirectViewer.start_desktop: only Stopped/Failed trigger an
    // engine start, so a flicker can't re-fire it and regenerate the SPICE password.
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STOPPED || current === DesktopStatusEnum.FAILED,
    baseMutation: startDesktopFromTokenMutation({ client: directViewerClient })
  })
)

const handleDesktopAction = (action: DesktopActionsEnum) => {
  switch (action) {
    case DesktopActionsEnum.Reset:
    case DesktopActionsEnum.Stop:
      showResetModal.value = true
      break
    case DesktopActionsEnum.Start:
      startDesktop(directViewerVars.value)
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
          <div class="flex flex-col items-center gap-10 animate-pulse">
            <div class="flex flex-col gap-1.5 items-center">
              <div class="h-3.5 w-40 rounded-md bg-gray-warm-200"></div>
              <div class="h-6 w-64 rounded-md bg-gray-warm-200"></div>
            </div>
            <DesktopCardSkeleton variant="started" class="shadow-lg h-[370px] w-[520px]" />
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
          <div class="flex flex-col items-center gap-10">
            <div class="flex flex-col gap-1.5 items-center">
              <p class="text-md text-left font-light text-gray-warm-800">
                {{ t('views.direct-viewer.connecting-to') }}
              </p>
              <h2 class="text-xl text-left font-semibold text-brand-700">
                {{ desktopViewer.name }}
              </h2>
            </div>
            <div class="flex gap-10 items-start">
              <div>
                <LoginNotification
                  v-if="loginConfig?.notification_cover?.enabled"
                  :config="loginConfig.notification_cover"
                />
                <div class="self-center relative">
                  <!-- Sized in % of the card so the dot field keeps the same bleed
                       around it at any breakpoint (viewBox is 900x520 for a 433x310 card). -->
                  <img
                    src="@/assets/img/bg-blue-dots.svg"
                    alt=""
                    aria-hidden="true"
                    class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[208%] h-[168%] max-w-none z-0 select-none pointer-events-none"
                  />
                  <DesktopCardBase
                    :desktop-kind="desktopCardKind"
                    :image-url="desktopViewer.image?.url ?? ''"
                    :show-overlay="activeOverlay !== null"
                    :fill-overlay="activeOverlay === 'info'"
                    class="shadow-lg relative z-10"
                    :size="CARD_SIZE"
                  >
                    <template #image>
                      <DirectViewerCardPreview
                        :status="desktopViewer.status"
                        :image-url="desktopViewer.image?.url ?? ''"
                        :vnc-values="vncValues"
                      />
                    </template>
                    <template #header-actions>
                      <DesktopCardOverlayButton
                        icon="info-circle"
                        title="components.desktops.desktop-card.actions.info"
                        :active="activeOverlay === 'info'"
                        @click="toggleOverlay('info')"
                      />
                      <DesktopCardOverlayButton
                        icon="modem-02"
                        title="components.desktops.desktop-card.actions.networks"
                        :active="activeOverlay === 'networks'"
                        @click="toggleOverlay('networks')"
                      />
                      <DesktopCardOverlayButton
                        v-if="bastion?.enabled"
                        icon="globe-04"
                        title="components.desktops.desktop-card.actions.bastion-access"
                        active-label="components.desktops.desktop-card.actions.bastion"
                        aria-label="components.desktops.desktop-card.actions.bastion-access"
                        :active="activeOverlay === 'bastion'"
                        @click="toggleOverlay('bastion')"
                      />
                    </template>
                    <template #ip>
                      <DesktopCardIp :desktop-status="desktopViewer.status" :desktop-ip="null" />
                    </template>
                    <template #overlay>
                      <div
                        v-if="activeOverlay === 'networks'"
                        :class="cardOverlayPaddingVariants({ size: CARD_SIZE })"
                        class="text-base-white text-start"
                      >
                        <DesktopCardNetworksOverlay
                          ref="networksOverlayRef"
                          :desktop-id="desktopViewer.id"
                          :desktop-status="desktopViewer.status"
                          :desktop-ip="desktopIp"
                          :direct-viewer-token="token"
                          :direct-viewer-client="directViewerClient"
                          :full-height="
                            !(notificationText && desktopViewer.description?.trim().length !== 0)
                          "
                          @show-networks-modal="showNetworksModal = true"
                        />
                        <div
                          v-if="!networksOverlayRef?.hasOverflow"
                          class="flex justify-end mt-1.5"
                        >
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <Button
                                hierarchy="link-gray"
                                size="sm"
                                class="h-6! px-2! gap-1 bg-base-white/15 hover:bg-base-white/30 font-semibold text-base-white"
                                :class="cardOverlayLabelVariants({ size: CARD_SIZE })"
                                @click="showNetworksModal = true"
                              >
                                {{ t('components.desktops.desktop-card.overlay.expand') }}
                                <Icon name="expand-04" size="xs" stroke-color="base-white" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent
                              :title="t('components.desktops.desktop-card.overlay.expand-tooltip')"
                            />
                          </Tooltip>
                        </div>
                      </div>
                      <DesktopCardBastionOverlay
                        v-else-if="activeOverlay === 'bastion'"
                        :bastion="bastion"
                        @show-bastion-modal="showBastionModal = true"
                      />
                      <DesktopCardInfoOverlay
                        v-else-if="activeOverlay === 'info'"
                        :desktop="desktopViewer"
                        :direct-viewer-token="token"
                        :direct-viewer-client="directViewerClient"
                        @show-info-modal="showDesktopInfoModal = true"
                      />
                    </template>
                    <template #header>
                      <DesktopCardHeader
                        :notification-text="notificationText"
                        :name="desktopViewer.name"
                        :description="desktopViewer.description || ''"
                        :hide-description="activeOverlay !== null"
                        :hide-notification="activeOverlay !== null"
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
            </div>
          </div>
        </template>
      </div>
    </main>
    <!-- `bastion` puts the card's modal in read-only mode: no queries, no editors. -->
    <DesktopBastionInfoModal
      v-if="showBastionModal && bastion && desktopViewer"
      :open="showBastionModal"
      :desktop-id="desktopViewer.id"
      :desktop-name="desktopViewer.name"
      :bastion="bastion"
      @close="showBastionModal = false"
    />
    <DesktopNetworksModal
      v-if="showNetworksModal && desktopViewer"
      :open="showNetworksModal"
      :desktop-id="desktopViewer.id"
      :desktop-name="desktopViewer.name"
      :desktop-status="desktopViewer.status"
      :desktop-ip="desktopIp"
      :direct-viewer-token="token"
      :direct-viewer-client="directViewerClient"
      @close="showNetworksModal = false"
    />
    <ChangeViewerModal
      :open="isViewerChangeModalOpen"
      :available-viewer-ids="viewerIds"
      :current-viewer-id="activeViewer ?? ''"
      @close="isViewerChangeModalOpen = false"
      @change="(id) => (selectedViewerId = id)"
    />
    <DomainInfoModal
      :open="showDesktopInfoModal"
      :domain-id="desktopViewer?.id"
      :name="desktopDetails?.name || desktopViewer?.name || ''"
      :description="desktopDetails?.description || ''"
      :status="desktopDetails?.status"
      :ip="desktopIp"
      :vcpu="desktopDetails?.vcpu"
      :ram="desktopDetails?.memory"
      :boot-order="desktopDetails?.boot_order?.map((bo) => bo.name)"
      :disk-bus="desktopDetails?.disk_bus?.name"
      :vga="desktopDetails?.videos?.map((v) => v.name)"
      :viewers="desktopDetails?.viewers"
      :isos="desktopDetails?.isos?.map((iso) => iso.name)"
      :floppies="desktopDetails?.floppies?.map((floppy) => floppy.name)"
      :reservables="desktopDetails?.reservables?.vgpus"
      :template="desktopDetails?.template"
      kind="desktop"
      :desktop-kind="desktopCardKind"
      :credentials="desktopDetails?.credentials"
      @close="showDesktopInfoModal = false"
    />
    <img
      src="@/assets/img/mountains.svg"
      alt=""
      aria-hidden="true"
      class="fixed bottom-0 right-0 -z-10 select-none pointer-events-none"
    />
    <img
      src="@/assets/img/clouds.svg"
      alt=""
      aria-hidden="true"
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
        <Button
          hierarchy="primary"
          size="lg"
          :disabled="isResetting"
          @click="resetDesktop(directViewerVars)"
        >
          {{ t('views.direct-viewer.reset-modal.confirm') }}
        </Button>
      </template>
    </AlertModal>
  </div>
</template>
