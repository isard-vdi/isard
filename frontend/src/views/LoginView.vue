<script setup lang="ts">
import { computed, type ComputedRef, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createClient, createConfig, type Options as ClientOptions } from '@hey-api/client-fetch'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { providersOptions } from '@/gen/oas/authentication/@tanstack/vue-query.gen'
import { login, type LoginData, type LoginError as AuthLoginError } from '@/gen/oas/authentication'
import type { GetCategoriesResponse } from '@/gen/oas/api'
import {
  getCategoriesOptions,
  getCategoriesQueryKey,
  getCategoryOptions,
  getCategoryQueryKey,
  getLoginConfigOptions
} from '@/gen/oas/api/@tanstack/vue-query.gen'
import {
  parseToken as parseAuthToken,
  getToken as getAuthToken,
  isCategorySelectClaims,
  isRegisterClaims,
  useCookies as useAuthCookies,
  isLoginClaims,
  setToken as setAuthToken,
  getBearer as getAuthBearer,
  removeToken as removeAuthToken,
  checkLoginRegister as checkAuthLoginRegister
} from '@/lib/auth'
import { dateIsToday } from '@/lib/utils'
import { Locale, setLocale } from '@/lib/i18n'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Provider,
  LoginProviderForm,
  LoginProviderExternal,
  LoginCategoriesDropdown,
  LoginCategorySelect,
  LoginNotification,
  isProvider
} from '@/components/login'
import { Separator } from '@/components/ui/separator'

const { t, te, d } = useI18n()
const route = useRoute()
const router = useRouter()
const cookies = useAuthCookies()
const queryClient = useQueryClient()

/*
 * Route arguments
 */
const routeProvider = computed(() => {
  const provider = Array.isArray(route.params.provider)
    ? route.params.provider[0]
    : route.params.provider
  if (provider === 'all') {
    return 'all'
  }

  // Check that the provider specified in the route is valid
  if (!isProvider(provider)) {
    // TODO: Router push to /login if the provider in the URL is invalid / not active / whatever
    return undefined
  }

  return provider
})

const routeCategory = computed(() => {
  const category = Array.isArray(route.params.category)
    ? route.params.category[0]
    : route.params.category

  return category !== '' ? category : undefined
})

/*
 * Data loading
 */
const {
  isPending: providersIsPending,
  isError: providersIsError,
  error: providersError,
  data: providers
} = useQuery(providersOptions())

const {
  isPending: configIsPending,
  isError: configIsError,
  error: configError,
  data: config
} = useQuery(getLoginConfigOptions())

const categoriesOpts = computed(() => getCategoriesOptions())
const categoriesQueryKey = computed(() => getCategoriesQueryKey())
const {
  isPending: categoriesIsPending,
  isError: categoriesIsError,
  error: categoriesError,
  data: categories
} = useQuery({
  ...categoriesOpts.value,
  queryKey: categoriesQueryKey,
  enabled: computed(() => !routeCategory.value)
})

const categoryOpts = computed(() =>
  getCategoryOptions({
    path: {
      custom_url: routeCategory.value || ''
    }
  })
)
const categoryQueryKey = computed(() =>
  getCategoryQueryKey({
    path: {
      custom_url: routeCategory.value || ''
    }
  })
)
const {
  isPending: categoryIsPending,
  isError: categoryIsError,
  error: categoryError,
  data: category
} = useQuery({
  ...categoryOpts.value,
  queryKey: categoryQueryKey,
  enabled: computed(() => !!routeCategory.value),
  retry: false
})

const isPending = computed(
  () =>
    providersIsPending.value ||
    configIsPending.value ||
    (categoriesIsPending.value && categoryIsPending.value)
)

const isError = computed(
  () =>
    providersIsError.value ||
    configIsError.value ||
    categoriesIsError.value ||
    categoryIsError.value
)
const error = computed(
  () => providersError.value || configError.value || categoriesError.value || categoryError.value
)

/*
 * View logic
 */
const showProvider = (provider: Provider): ComputedRef<boolean> =>
  computed(() => {
    // Check that the provider is enabled by authentication
    if (!providers.value?.providers.includes(provider)) {
      return false
    }

    // If there's a provider on the route, show it if it corresponds
    if (routeProvider.value) {
      return routeProvider.value === 'all' ? true : provider === routeProvider.value
    }

    // If the providers are limited in the login configuration, follow this config
    const displayProviders = config.value?.providers?.all?.display_providers
    if (displayProviders) {
      return displayProviders.includes(provider)
    }

    // Otherwise, display the provider
    return true
  })

const providersToShow = computed(() =>
  Object.values(Provider).filter((provider) => showProvider(provider).value)
)

const showCategoriesDropdown = computed(() => {
  let display = true

  // If there's a category set in the URL, don't show the dropdown
  if (routeCategory.value) {
    return false
  }

  // If there is only one category, don't show the dropdown
  if (categories.value?.length === 1) {
    return false
  }

  const providersConfig = config.value?.providers
  if (providersConfig) {
    // Check if there's a general hide
    if (providersConfig.all?.hide_categories_dropdown) {
      display = false
    }

    // If there's an active provider, check the configuration for it
    if (routeProvider.value) {
      const hide = providersConfig[routeProvider.value]?.hide_categories_dropdown
      if (hide !== undefined) {
        display = !hide
      }

      // Otherwise, check the other providers
    } else {
      for (const provider of providersToShow.value) {
        const hide = providersConfig[provider]?.hide_categories_dropdown
        if (hide !== undefined) {
          // If there's a provider that explicitelly enables the category dropdown,
          // takes preference over the rest
          if (!hide) {
            break
          }

          display = !hide
        }
      }
    }
  }

  return display
})

const categoriesDropdownModel = ref<GetCategoriesResponse[number] | undefined>(undefined)
const selectedCategory = computed(() => {
  if (category.value) {
    return category.value.id
  }

  // If the dropdown is shown, always use this value
  if (showCategoriesDropdown.value) {
    return categoriesDropdownModel.value ? categoriesDropdownModel.value.id : undefined
  }

  // If there's only one category, use it
  if (categories.value?.length === 1) {
    return categories.value[0].id
  }

  // Fallback to the 'default' category if there's no category
  // in the URL and the dropdown isn't shown. This is useful for
  // external providers that can guess the category
  return 'default'
})

const categoriesDropdownEl = ref<InstanceType<typeof LoginCategoriesDropdown> | null>(null)
const focusCategoriesDropdown = () => {
  loginError.value = 'missing_category'
  categoriesDropdownEl.value?.focus()
}

const description = computed(() => {
  let description: string | undefined = undefined
  if (config.value?.providers?.all?.description) {
    description = config.value.providers.all.description
  }

  if (providersToShow.value.length === 1) {
    if (config.value?.providers?.[providersToShow.value[0]]?.description) {
      description = config.value.providers[providersToShow.value[0]]?.description
    }
  }

  return description
})

// TODO: Type this!
type LoginError = AuthLoginError['error'] | 'unknown' | 'missing_category'

const isLoginError = (error: string): error is LoginError => {
  switch (error) {
    case 'unknown':
    case 'missing_category':
    case 'invalid_credentials':
    case 'user_disabled':
    case 'user_disallowed':
    case 'rate_limit':
      return true

    default:
      return false
  }
}

const loginError = ref<LoginError | undefined>(
  (() => {
    const error = Array.isArray(route.query.error) ? route.query.error[0] : route.query.error
    if (!error || error === '') {
      return undefined
    }

    if (!isLoginError(error)) {
      return 'unknown'
    }

    return error
  })()
)
const loginErrorParams = ref<Date | undefined>(undefined)
const loginErrorMsg = computed(() => {
  const baseKey = 'authentication.login.errors.'
  const key = baseKey + loginError.value

  // Check if the error exists in the base locale
  if (te(key, 'en-US')) {
    // If the error is a rate_limit_date error, show the extra parameters
    if (loginError.value === 'rate_limit_date' && loginErrorParams.value) {
      let timeParam = d(loginErrorParams.value, {
        hour: 'numeric',
        minute: 'numeric',
        second: 'numeric'
      })

      if (!dateIsToday(loginErrorParams.value)) {
        timeParam = d(loginErrorParams.value, {
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

const categorySelectToken = computed(() => {
  const token = getAuthToken(cookies)
  if (!token || !isCategorySelectClaims(token)) {
    return undefined
  }

  return token.categories
})

/*
 * Actions
 */
const submitLogin = async (options: ClientOptions<LoginData>) => {
  // Cleanup old tokens
  removeAuthToken(cookies)

  const { error, response } = await login(options)
  const check = checkAuthLoginRegister(error, response)
  if (check !== undefined) {
    if (check.error) {
      loginError.value = check.error
    }
    if (check.errorParams) {
      loginErrorParams.value = check.errorParams
    }
    return
  }

  const authorization = response.headers.get('authorization')
  if (authorization === null) {
    loginError.value = 'unknown'
    return
  }

  const bearer = authorization.replace(/^Bearer /g, '')
  if (bearer.length === authorization.length) {
    loginError.value = 'unknown'
    return
  }

  const jwt = parseAuthToken(bearer)
  if (isCategorySelectClaims(jwt)) {
    return
  }

  if (isRegisterClaims(jwt)) {
    router.push({ name: 'register' })
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

const onFormSubmit = async (values) => {
  loginError.value = undefined

  if (!selectedCategory.value) {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'missing_category'
    return
  }

  await submitLogin({
    body: values,
    query: {
      category_id: selectedCategory.value,
      provider: 'form'
    }
  })
}

const onExternalSubmit = async (provider: Provider) => {
  loginError.value = undefined

  if (!selectedCategory.value) {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'missing_category'
    return
  }

  const data: LoginData = {
    query: {
      category_id: selectedCategory.value,
      provider: provider,
      redirect: '/'
    }
  }

  const url = new URL('/authentication/login', window.location.origin)
  for (const [k, v] of Object.entries(data.query)) {
    url.searchParams.set(k, v)
  }

  // We need to create a form in order to do a POST
  // request, with multipart/form-data in the window
  // of the browser instead of a threaded request
  const form = document.createElement('form')
  document.body.appendChild(form)
  form.method = 'POST'
  form.enctype = 'multipart/form-data'
  form.action = url.toString()
  form.submit()
}

const onCategorySelectSubmit = async (categoryId: string) => {
  // We extract it outside the interceptor, because afterwards will get deleted
  const bearer = getAuthBearer(cookies)

  await submitLogin({
    headers: {
      Authorization: 'Bearer ' + bearer
    },
    query: {
      category_id: categoryId,
      provider: 'form'
    }
  })
}

const onForgotPassword = () => {
  loginError.value = undefined

  if (!selectedCategory.value) {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'missing_category'
    return
  }

  window.location.href = '/forgot-password?categoryId=' + selectedCategory.value
}

/*
 * Watchers
 */

// Redirect to the maintenance page if there's a maintenance error
watch(error, (newErr) => {
  if (newErr && newErr.message.includes('503')) {
    window.location.href = '/maintenance'
  }
})

// Set the locale if there's a configuration set
watch(config, (newCfg) => {
  if (newCfg?.locale?.default) {
    setLocale(newCfg.locale.default as Locale)
    localStorage.language = newCfg.locale.default
  }
})

watch(categoryError, (newErr) => {
  if (newErr && JSON.parse(newErr.message).error === 'not_found') {
    router
      .push({
        name: 'login',
        params: {
          provider: routeProvider.value
        }
      })
      .then(() => {
        queryClient.invalidateQueries({ queryKey: categoryQueryKey.value })
      })
  }
})
</script>

<template>
  <LoginLayout
    :loading="isPending"
    :hide-locale-switch="config?.locale?.hide"
    :hide-logo="config?.logo?.hide"
    :title="category?.name || config?.info?.title"
    :description="categorySelectToken ? t('views.login.select-category') : description"
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
          <Alert v-if="loginError" variant="destructive">
            <AlertDescription>{{ loginErrorMsg }}</AlertDescription>
          </Alert>

          <LoginCategorySelect
            v-if="categorySelectToken"
            :categories="categorySelectToken"
            @submit="onCategorySelectSubmit"
          />

          <template v-else>
            <LoginCategoriesDropdown
              v-if="showCategoriesDropdown"
              ref="categoriesDropdownEl"
              v-model:model-value="categoriesDropdownModel"
              :categories="categories || []"
            />

            <LoginProviderForm
              v-if="showProvider(Provider.Form).value"
              :text="config?.providers?.form?.submit_text"
              :hide-forgot-password="config?.providers?.form?.hide_forgot_password"
              :style="config?.providers?.form?.submit_extra_styles"
              @submit="onFormSubmit"
              @forgot-password="onForgotPassword"
            />

            <Separator
              v-if="providersToShow.length > 1 && providersToShow.includes(Provider.Form)"
              :label="t('views.login.separator')"
            />

            <template v-for="provider in providersToShow" :key="provider">
              <LoginProviderExternal
                v-if="provider !== Provider.Form"
                :provider="provider"
                :text="config?.providers?.[provider]?.submit_text"
                :icon="config?.providers?.[provider]?.submit_icon"
                :style="config?.providers?.[provider]?.submit_extra_styles"
                @submit="onExternalSubmit"
              />
            </template>
          </template>
        </template>
      </div>
    </template>
  </LoginLayout>
</template>
