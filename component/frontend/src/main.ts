import './assets/index.css'
import '@fontsource-variable/montserrat'
import '@fontsource/fira-mono'

// Must run before any module that constructs zod schemas at import time.
import './lib/zod-config'

import { computed, createApp } from 'vue'
import { createPinia } from 'pinia'

import { client as authClient } from './gen/oas/authentication/client.gen'
import { client as apiClient } from './gen/oas/api/client.gen'
import { client as apiv4Client } from './gen/oas/apiv4/client.gen'

import App from './App.vue'
import router from './router'
import { i18n, setBrowserLocale, setLocale } from './lib/i18n'
import { VueQueryPlugin, type VueQueryPluginOptions } from '@tanstack/vue-query'
import { useAuthStore } from './stores/auth'
import { checkTokenBeforeRequest } from './lib/interceptor'
import { setupZodI18n } from './lib/zod-i18n'

// Configure Authentication OAS client
authClient.setConfig({
  baseUrl: '/authentication'
})

import { watch } from 'vue'

localStorage.language ? setLocale(localStorage.language) : setBrowserLocale(i18n)

// Setup Zod global error map with i18n
setupZodI18n(i18n.global)

const vueQueryPluginOptions: VueQueryPluginOptions = {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        staleTime: 30000
      }
    }
  },
  enableDevtoolsV6Plugin: true
}

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
const authStore = useAuthStore()
authStore.initialize()

// Register interceptors once (outside the watch to avoid stacking)
apiv4Client.interceptors.request.use(async (config) => {
  if (!authStore.token) {
    return config
  }

  // Ignore if calling either a public route or the logout or renew route
  if (config.url?.includes('/logout') || config.url?.includes('/renew')) {
    return config
  }

  // Check token before each request
  const tokenValid = await checkTokenBeforeRequest()

  if (!tokenValid) {
    throw new Error('Authentication required')
  }

  // Update config with current token directly
  const currentToken = authStore.token
  if (currentToken && config.headers) {
    config.headers.set('Authorization', `Bearer ${currentToken}`)
  }

  return config
})

apiv4Client.interceptors.response.use(async (response) => {
  if (response.status === 401) {
    // Handle unauthorized response, e.g., by logging out the user
    authStore.logout()
  }
  return response
})

// Configure API OAS client headers on token changes
watch(
  () => authStore.token,
  (newToken) => {
    const headers = newToken ? { Authorization: `Bearer ${newToken}` } : undefined

    authClient.setConfig({
      headers
    })
    apiClient.setConfig({
      headers
    })
    apiv4Client.setConfig({
      headers
    })
  },
  { immediate: true }
)

app.use(router)
app.use(i18n)
app.use(VueQueryPlugin, vueQueryPluginOptions)

app.mount('#app')
