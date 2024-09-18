<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { type Options as ClientOptions } from '@hey-api/client-fetch'
import { useQuery } from '@tanstack/vue-query'
import { login, type LoginData, type LoginError as AuthLoginError } from '@/gen/oas/authentication'
import { registerUser, type RegisterUserData, type RegisterUserError } from '@/gen/oas/api'
import { getLoginConfigOptions } from '@/gen/oas/api/@tanstack/vue-query.gen'
import {
  parseToken as parseAuthToken,
  getToken as getAuthToken,
  isCategorySelectClaims,
  useCookies as useAuthCookies,
  isLoginClaims,
  setToken as setAuthToken,
  getBearer as getAuthBearer,
  removeToken as removeAuthToken,
  isRegisterClaims,
  checkLoginRegister as checkAuthLoginRegister
} from '@/lib/auth'
import { dateIsToday } from '@/lib/utils'
import { Locale, setLocale } from '@/lib/i18n'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { Provider, LoginNotification } from '@/components/login'
import { RegisterForm } from '@/components/register'

const { t, te, d } = useI18n()
const route = useRoute()
const router = useRouter()
const cookies = useAuthCookies()

/*
 * Data loading
 */
const {
  isPending: configIsPending,
  isError: configIsError,
  error: configError,
  data: config
} = useQuery(getLoginConfigOptions())

const isPending = computed(() => configIsPending.value)

const isError = computed(() => configIsError.value)
const error = computed(() => configError.value)

/*
 * View logic
 */
// TODO: Type this!
type RegisterError =
  | RegisterUserError['error']
  | AuthLoginError['error']
  | 'unknown'
  | 'missing_category'

const isregisterError = (error: string): error is RegisterError => {
  switch (error) {
    case 'unknown':
    case 'missing_category':
    case 'invalid_credentials':
    case 'user_disabled':
    case 'user_disallowed':
    case 'forbidden':
    case 'not_found':
    case 'conflict':
    case 'rate_limit':
      return true

    default:
      return false
  }
}

const registerError = ref<RegisterError | undefined>(
  (() => {
    const error = Array.isArray(route.query.error) ? route.query.error[0] : route.query.error
    if (!error || error === '') {
      return undefined
    }

    if (!isregisterError(error)) {
      return 'unknown'
    }

    return error
  })()
)

const registerErrorParams = ref<Date | undefined>(undefined)
const registerErrorMsg = computed(() => {
  const registerBaseKey = 'api.register.errors.'
  const registerKey = registerBaseKey + registerError.value

  // Check if the error exists in the base locale
  if (te(registerKey, 'en-US')) {
    // If the error is a rate_limit error, show the extra parameters
    if (registerError.value === 'rate_limit' && registerErrorParams.value) {
      let timeParam = d(registerErrorParams.value, {
        hour: 'numeric',
        minute: 'numeric',
        second: 'numeric'
      })

      if (!dateIsToday(registerErrorParams.value)) {
        timeParam = d(registerErrorParams.value, {
          day: 'numeric',
          month: 'numeric',
          year: 'numeric',
          hour: 'numeric',
          minute: 'numeric',
          second: 'numeric'
        })
      }
      return t(registerKey, { time: timeParam })
    }

    return t(registerKey)
  }

  // check login errors if register error is not found
  const baseKey = 'authentication.login.errors.'
  const key = baseKey + registerError.value

  // Check if the error exists in the base locale
  if (te(key, 'en-US')) {
    // If the error is a rate_limit_date error, show the extra parameters
    if (registerError.value === 'rate_limit_date' && registerErrorParams.value) {
      let timeParam = d(registerErrorParams.value, {
        hour: 'numeric',
        minute: 'numeric',
        second: 'numeric'
      })

      if (!dateIsToday(registerErrorParams.value)) {
        timeParam = d(registerErrorParams.value, {
          day: 'numeric',
          month: 'numeric',
          year: 'numeric',
          hour: 'numeric',
          minute: 'numeric',
          second: 'numeric'
        })
      }
      return t(key, { time: timeParam })
    }

    return t(key)
  }

  return t(baseKey + 'unknown')
})

const isRegisterToken = () => {
  const token = getAuthToken(cookies)
  if (!token || !isRegisterClaims(token)) {
    return false
  }
  return true
}

/*
 * Actions
 */
const submitLogin = async (options: ClientOptions<LoginData>) => {
  // Cleanup old tokens
  removeAuthToken(cookies)

  const { error, response } = await login(options)
  const check = checkAuthLoginRegister(error, response)
  if (check) {
    if (check.error) {
      registerError.value = check.error
    }
    if (check.errorParams) {
      registerErrorParams.value = check.errorParams
    }
    return
  }

  const authorization = response.headers.get('authorization')
  if (authorization === null) {
    registerError.value = 'unknown'
    return
  }

  const bearer = authorization.replace(/^Bearer /g, '')
  if (bearer.length === authorization.length) {
    registerError.value = 'unknown'
    return
  }

  const jwt = parseAuthToken(bearer)
  if (isCategorySelectClaims(jwt)) {
    return
  }

  if (isLoginClaims(jwt)) {
    // Login to Webapp
    if (['admin', 'manager'].includes(jwt.data.role_id)) {
      try {
        await fetch('/isard-admin/login', {
          method: 'POST',
          headers: {
            Authorization: authorization
          }
        })
      } catch (error) {
        // If there's an error logging to Webapp, log it and continue.
        // It probably is a 503, because is in maintenance
        console.error(error)
      }
    }
  }

  setAuthToken(cookies, bearer)
  window.location.pathname = '/'
}

const submitRegister = async (options: ClientOptions<RegisterUserData>) => {
  const bearer = getAuthBearer(cookies) ?? ''

  const { error, response } = await registerUser({
    ...options,
    headers: { Authorization: `Bearer ${bearer}` }
  })
  const err = checkAuthLoginRegister(error, response, true)
  if (err) {
    if (err.error) {
      registerError.value = err.error
    }
    if (err.errorParams) {
      registerErrorParams.value = err.errorParams
    }
    return
  }

  // setAuthToken(cookies, bearer)
  const registeredUser = parseAuthToken(bearer)

  if (isRegisterClaims(registeredUser)) {
    if (registeredUser.provider === 'local' || registeredUser.provider === 'ldap') {
      registeredUser.provider = 'form'
    }

    await submitLogin({
      headers: {
        Authorization: 'Bearer ' + bearer
      },
      query: {
        category_id: registeredUser.category_id,
        provider: registeredUser.provider as Provider
      }
    })
  }
}

const onSubmit = async (values: any) => {
  registerError.value = undefined

  await submitRegister({
    body: values
  })
}

const onCancel = () => {
  // Cleanup old tokens
  removeAuthToken(cookies)

  registerError.value = undefined

  router.push({
    name: 'login'
  })
}

/*
 * Watchers
 */

// Redirect to the maintenance page if there's a maintenance error
watch(error, (newErr) => {
  if (newErr && newErr.message.includes('503')) {
    window.location.pathname = '/maintenance'
  }
})

// Redirect to '/' if the token is not a register token
onMounted(() => {
  if (!isRegisterToken()) {
    window.location.pathname = '/'
  }
})
watch(cookies, (newCookies) => {
  const token = getAuthToken(newCookies)
  if (!token || !isRegisterClaims(token)) {
    window.location.pathname = '/'
  }
})

// Set the locale if there's a configuration set
watch(config, (newCfg) => {
  if (newCfg?.locale?.default) {
    setLocale(newCfg.locale.default as Locale)
  }
})
</script>

<template>
  <LoginLayout
    :loading="isPending"
    :hide-locale-switch="config?.locale?.hide"
    :hide-logo="config?.logo?.hide"
    :title="t('views.register.title')"
  >
    <template v-if="config?.notification_cover" #cover>
      <LoginNotification :config="config.notification_cover" class="border-error-600" />
    </template>

    <template #default>
      <div class="flex flex-col space-y-4">
        <Skeleton v-if="isPending" class="h-6" />

        <Alert v-else-if="isError" variant="destructive">{{
          t('authentication.login.errors.unknown')
        }}</Alert>

        <template v-else>
          <LoginNotification v-if="config?.notification_form" :config="config.notification_form" />
          <Alert v-if="registerError" variant="destructive">
            <AlertDescription>{{ registerErrorMsg }}</AlertDescription>
          </Alert>

          <RegisterForm
            v-if="isRegisterToken()"
            :text="config?.providers?.form?.submit_text"
            :style="config?.providers?.form?.submit_extra_styles"
            @submit="onSubmit"
            @cancel="onCancel"
          />
        </template>
      </div>
    </template>
  </LoginLayout>
</template>
