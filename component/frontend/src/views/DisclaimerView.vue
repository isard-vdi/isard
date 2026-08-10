<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { apiV4DisclaimerOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { acknowledgeDisclaimer, login } from '@/gen/oas/authentication'
import {
  parseToken as parseAuthToken,
  isLoginClaims,
  useCookies as useAuthCookies,
  setToken as setAuthToken,
  checkLoginRegister as checkAuthLoginRegister
} from '@/lib/auth'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import mountainsSvg from '@/assets/img/mountains.svg'
import { Separator } from '@/components/ui/separator'
import LogoSvg from '@/assets/logo.svg?url'

const { t } = useI18n()
const router = useRouter()
const cookies = useAuthCookies()
const authStore = useAuthStore()

const error = ref<string | undefined>(undefined)
const isAccepting = ref(false)

const { data: disclaimer, isPending } = useQuery(apiV4DisclaimerOptions())

// The disclaimer body/footer are admin-authored HTML rendered via v-html;
// sanitize them with DOMPurify to prevent stored-XSS.
const sanitizedBody = computed(() =>
  disclaimer.value?.body ? DOMPurify.sanitize(disclaimer.value.body) : ''
)
const sanitizedFooter = computed(() =>
  disclaimer.value?.footer ? DOMPurify.sanitize(disclaimer.value.footer) : ''
)

const accept = async () => {
  error.value = undefined
  isAccepting.value = true

  try {
    // Step 1: Acknowledge the disclaimer
    const ackResponse = await acknowledgeDisclaimer({ body: {} })
    if (ackResponse.error) {
      error.value = 'acknowledge_failed'
      isAccepting.value = false
      return
    }

    // Step 2: Login again — the disclaimer token is still in the cookie
    // and is sent automatically as Authorization
    const { error: loginErr, response } = await login({
      query: { provider: 'form', category_id: '' },
      body: {}
    })

    const check = checkAuthLoginRegister(loginErr, response)
    if (check !== undefined) {
      error.value = check.error || 'unknown'
      isAccepting.value = false
      return
    }

    const authorization = response.headers.get('authorization')
    if (authorization === null) {
      error.value = 'unknown'
      isAccepting.value = false
      return
    }

    const bearer = authorization.replace(/^Bearer /g, '')
    if (bearer.length === authorization.length) {
      error.value = 'unknown'
      isAccepting.value = false
      return
    }

    const jwt = parseAuthToken(bearer)

    if (isLoginClaims(jwt)) {
      // Calculate and store time drift for session management
      const serverTime = jwt.iat * 1000
      const localTime = Date.now()
      let drift = serverTime - localTime

      // Maximum allowed drift: 24 hours in either direction
      const MAX_DRIFT = 24 * 60 * 60 * 1000
      if (Math.abs(drift) > MAX_DRIFT) {
        console.warn(`Extreme time drift detected: ${drift}ms. Changing to a safe range.`)
        drift = drift > 0 ? MAX_DRIFT : -MAX_DRIFT
      }

      localStorage.setItem('auth_time_drift', drift.toString())

      // Login to Webapp
      if (['admin', 'manager'].includes(jwt.data.role_id)) {
        try {
          await fetch('/isard-admin/login', {
            method: 'POST',
            headers: { Authorization: authorization }
          })
        } catch (err) {
          console.error(err)
        }
      }
    }

    setAuthToken(cookies, bearer)

    const location = response.headers.get('location')
    if (location) {
      if (location.startsWith('/notifications/')) {
        router.push(location)
        return
      }
      window.location.pathname = location
      return
    }

    window.location.pathname = '/'
  } catch (err) {
    console.error('Disclaimer accept failed:', err)
    error.value = 'unknown'
    isAccepting.value = false
  }
}

const reject = () => {
  authStore.logout()
  router.push({ name: 'login' })
}

const logoSrc = ref('/api/v4/logo')
const handleLogoError = () => (logoSrc.value = LogoSvg)
</script>

<template>
  <div class="relative min-h-screen w-full overflow-hidden bg-base-background">
    <!-- Disclaimer card -->
    <div
      class="relative z-2 mx-8 my-16 h-[calc(100vh-8rem)] rounded-3xl border border-gray-warm-300 bg-base-white shadow-xl overflow-hidden"
    >
      <div class="h-full overflow-y-auto pt-5 px-5 text-justify md:px-12 md:pt-10">
        <div class="mx-auto md:w-3/4">
          <!-- Logo -->
          <img
            class="mb-8 flex m-auto max-h-30"
            :src="logoSrc"
            @error="handleLogoError"
            alt="logo"
          />
          <!-- Loading -->
          <div v-if="isPending" class="flex flex-col gap-4">
            <div class="h-8 w-3/4 bg-gray-warm-200 rounded animate-pulse" />
            <div class="h-40 w-full bg-gray-warm-200 rounded animate-pulse" />
          </div>
          <!-- Content -->
          <div v-else-if="disclaimer" class="flex flex-col gap-4">
            <h2 class="text-[30px] font-bold text-gray-warm-800 mb-2 leading-9">
              {{ disclaimer.title }}
            </h2>
            <!-- eslint-disable vue/no-v-html -- content sanitized via DOMPurify -->
            <div class="disclaimer-body text-md text-gray-warm-600" v-html="sanitizedBody" />
            <Separator />
            <div
              v-if="sanitizedFooter"
              class="text-sm text-gray-warm-500"
              v-html="sanitizedFooter"
            />
            <!-- eslint-enable vue/no-v-html -->
            <Alert v-if="error" variant="destructive">
              <AlertDescription>
                {{ t('views.disclaimer.error') }}
              </AlertDescription>
            </Alert>
            <div class="flex justify-end gap-3 mb-6">
              <Button hierarchy="destructive" size="md" @click="reject">
                {{ t('views.disclaimer.reject') }}
              </Button>
              <Button hierarchy="primary" size="md" :loading="isAccepting" @click="accept">
                {{ t('views.disclaimer.accept') }}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Mountains background -->
    <img :src="mountainsSvg" class="fixed bottom-0 right-0 z-1 pointer-events-none" alt="" />
  </div>
</template>

<style>
.disclaimer-body h4 {
  font-size: 22px;
  font-weight: 500;
  margin: 15px 0px 7px;
}

.disclaimer-body ul {
  list-style: disc;
  padding-left: 35px;
}
</style>
