<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RdpConnectionState } from '@/lib/guacamole/states'
import { BrandLogo } from '@/components/logo'
import { Alert, AlertDescription, AlertTitle, type AlertVariants } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'

interface Props {
  state: RdpConnectionState
  retry?: number
  maxRetries?: number
  desktopName?: string
}

const { state, retry = 0, maxRetries = 0, desktopName } = defineProps<Props>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()

interface StateStyle {
  variant: AlertVariants['variant']
  color: 'error' | 'warning' | 'gray'
  icon: string
}

const STATE_COPY: Record<RdpConnectionState, string> = {
  [RdpConnectionState.IDLE]: 'connecting',
  [RdpConnectionState.CONNECTING]: 'connecting',
  [RdpConnectionState.WAITING]: 'connecting',
  [RdpConnectionState.CONNECTED]: 'connecting',
  [RdpConnectionState.RETRYING]: 'retrying',
  [RdpConnectionState.DISCONNECTED]: 'disconnected',
  [RdpConnectionState.CLIENT_ERROR]: 'error',
  [RdpConnectionState.TUNNEL_ERROR]: 'error',
  [RdpConnectionState.COOKIE_ERROR]: 'cookie-error',
  [RdpConnectionState.VIEWER_TOKEN_ERROR]: 'viewer-token-error',
  [RdpConnectionState.COOKIE_EXPIRED]: 'cookie-expired',
  [RdpConnectionState.RDP_NOT_RUNNING]: 'rdp-not-running',
  [RdpConnectionState.RDP_AUTH_FAILED]: 'rdp-auth-failed',
  [RdpConnectionState.DESKTOP_STOPPED]: 'desktop-stopped'
}

const LOADING_STATES = new Set<RdpConnectionState>([
  RdpConnectionState.IDLE,
  RdpConnectionState.CONNECTING,
  RdpConnectionState.WAITING,
  RdpConnectionState.CONNECTED,
  RdpConnectionState.RETRYING
])

const STATE_STYLES: Partial<Record<RdpConnectionState, StateStyle>> = {
  [RdpConnectionState.DISCONNECTED]: { variant: 'default', color: 'gray', icon: 'wifi-off' },
  [RdpConnectionState.DESKTOP_STOPPED]: {
    variant: 'warning',
    color: 'warning',
    icon: 'stop-circle'
  }
}

const ERROR_STYLE: StateStyle = { variant: 'destructive', color: 'error', icon: 'alert-circle' }

const loading = computed(() => LOADING_STATES.has(state))
const copyKey = computed(() => `views.rdp.states.${STATE_COPY[state]}`)
const stateStyle = computed(() => STATE_STYLES[state] ?? ERROR_STYLE)
const retriesExhausted = computed(() => maxRetries > 0 && retry === maxRetries)
</script>

<template>
  <div class="fixed inset-0 z-10 flex flex-col overflow-hidden bg-base-background">
    <header
      class="flex h-16 shrink-0 items-center justify-between px-6 border-b border-gray-warm-300 bg-base-background"
    >
      <h1 class="text-display-xs font-semibold text-gray-warm-900">
        {{ t('views.rdp.header') }}
      </h1>
      <BrandLogo class="max-h-10 max-w-45 w-auto object-contain" />
    </header>
    <main class="flex flex-1 flex-col items-center justify-center gap-10 px-4">
      <div v-if="desktopName" class="flex flex-col items-center gap-1.5 text-center">
        <p class="text-lg font-light text-gray-warm-800">
          {{ t('views.rdp.accessing-desktop') }}
        </p>
        <h2 class="text-display-sm font-semibold text-brand-700 wrap-break-word">
          {{ desktopName }}
        </h2>
      </div>
      <div class="relative w-full max-w-xl">
        <!-- Fixed size: the alert's height changes with the state, and the dots must not shrink with it. -->
        <img
          src="@/assets/img/bg-blue-dots.svg"
          alt=""
          aria-hidden="true"
          class="absolute left-1/2 top-1/2 -z-10 h-130 w-225 max-w-none -translate-x-1/2 -translate-y-1/2 select-none pointer-events-none"
        />
        <Alert :variant="loading ? 'default' : stateStyle.variant" class="w-full">
          <div v-if="loading" class="icon flex size-10 items-center justify-center">
            <Spinner size="sm" class="size-8 text-brand-600" />
          </div>
          <FeaturedIconOutline
            v-else
            kind="outline"
            :color="stateStyle.color"
            :name="stateStyle.icon"
          />
          <AlertTitle class="font-bold text-gray-warm-700 mb-2">
            {{ t(`${copyKey}.title`) }}
          </AlertTitle>
          <AlertDescription>
            {{ t(`${copyKey}.message`, { retry, maxRetries }) }}
          </AlertDescription>
          <Button
            v-if="!loading"
            size="sm"
            hierarchy="primary"
            icon="refresh-cw-01"
            class="mt-4"
            @click="emit('reload')"
          >
            {{ t(retriesExhausted ? 'views.rdp.buttons.retry' : 'views.rdp.buttons.refresh') }}
          </Button>
        </Alert>
      </div>
    </main>
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
  </div>
</template>
