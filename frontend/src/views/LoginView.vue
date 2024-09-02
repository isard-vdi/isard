<script setup lang="ts">
import { computed, type ComputedRef, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createClient, createConfig, type Options as ClientOptions } from '@hey-api/client-fetch'
import { useQuery } from '@tanstack/vue-query'
import { providersOptions } from '@/gen/oas/authentication/@tanstack/vue-query.gen'
import { login, type LoginData } from '@/gen/oas/authentication'
import { getCategoriesOptions, getLoginConfigOptions } from '@/gen/oas/api/@tanstack/vue-query.gen'
import {
  parseToken as parseAuthToken,
  getToken as getAuthToken,
  isCategorySelectClaims,
  useCookies as useAuthCookies,
  isLoginClaims,
  setToken as setAuthToken,
  getBearer as getAuthBearer,
  removeToken as removeAuthToken
} from '@/lib/auth'
import { dateIsToday } from '@/lib/utils'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import {
  Provider,
  LoginProviderForm,
  LoginProviderExternal,
  LoginCategoriesDropdown,
  LoginCategorySelect,
  isProvider
} from '@/components/login'
import { Separator } from '@/components/ui/separator'
import { Icon } from '@/components/icon'
import { i18n, setLocale } from '@/lib/i18n'

const { t, te, d } = useI18n()
const route = useRoute()
const cookies = useAuthCookies()

const {
  isPending: providersIsPending,
  isError: providersIsError,
  error: providersError,
  data: providers
} = useQuery(providersOptions())

const {
  isPending: categoriesIsPending,
  isError: categoriesIsError,
  error: categoriesError,
  data: categories
} = useQuery(getCategoriesOptions())

const {
  isPending: configIsPending,
  isError: configIsError,
  error: configError,
  data: config
} = useQuery(getLoginConfigOptions())

const isPending = computed(
  () => providersIsPending.value || categoriesIsPending.value || configIsPending.value
)
const isError = computed(() => providersIsError.value || categoriesIsError.value || configIsError.value)
const error = computed(() => {
  if (providersIsError.value) {
    return providersError.value
  }

  if (categoriesIsError.value) {
    return categoriesError.value
  }

  if (configIsError.value) {
    return configError.value
  }

  return undefined
})

const routeProvider = computed(() => {
  const provider = Array.isArray(route.params.provider) ? route.params.provider[0] : route.params.provider
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
  const category = Array.isArray(route.params.category) ? route.params.category[0] : route.params.category

  // Check that the category specified in the route is valid
  if (category === '' || isPending.value || !categories.value) {
    // TODO: Router push to /login/provider if the category invalid / not active / whatever
    return undefined
  }

  // Check that the category specified in the route is an existing category
  let found = false
  for (const c of categories.value) {
    if (c.custom_url_name === category) {
      found = true
      break
    }
  }

  if (!found) {
    return undefined
  }

  return category
})

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

  // If there's a category set in the URL, don't show the dropdown
  if (routeCategory.value) {
    display = false
  }

  return display
})

const categoriesDropdownModel = ref('')
const category = computed(() => {
  if (routeCategory.value) {
    return routeCategory.value
  }

  // If the dropdown is shown, always use this value
  if (showCategoriesDropdown.value) {
    return categoriesDropdownModel.value
  }

  // Fallback to the 'default' category if there's no category
  // in the URL and the dropdown isn't shown. This is useful for
  // external providers that can guess the category
  return 'default'
})

const categoriesDropdownEl = ref<InstanceType<typeof LoginCategoriesDropdown> | null>(null)
const focusCategoriesDropdown = () => {
  categoriesDropdownEl.value?.focus()
}

const loginError = ref((() => {
  const error = Array.isArray(route.query.error) ? route.query.error[0] : route.query.error
  if (!error || error === '') {
    return undefined
  }

  return error
})())
const loginErrorParams = ref<Date | undefined>(undefined)
const loginErrorMsg = computed(() => {
  const baseKey = 'authentication.login.errors.'
  const key = baseKey + loginError.value

  // Check if the error exists in the base locale
  if (te(key, 'en-US')) {
    // If the error is a rate_limit error, show the extra parameters
    if (loginError.value === 'rate_limit' && loginErrorParams.value) {
      let timeParam = d(loginErrorParams.value, { hour: 'numeric', minute: 'numeric', second: 'numeric' })

      if (!dateIsToday(loginErrorParams.value)) {
        timeParam = d(loginErrorParams.value, {
          day: 'numeric', month: 'numeric', year: 'numeric',
          hour: 'numeric', minute: 'numeric', second: 'numeric'
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

const submitLogin = async (options: ClientOptions<LoginData>) => {
  // Cleanup old tokens
  removeAuthToken(cookies)

  const { error, response } = await login(options)
  if (error !== undefined) {
    if (response.status === 429) {
      loginError.value = 'rate_limit'
      loginErrorParams.value = new Date(response.headers.get('retry-after'))
      return
    }

    loginError.value = error.error
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

  if (isLoginClaims(jwt)) {
    // Login to Webapp
    if (['admin', 'manager'].includes(jwt.data.role_id)) {
      await fetch('/isard-admin/login', {
        method: 'POST',
        headers: {
          Authorization: authorization
        }
      })
    }
  }

  setAuthToken(cookies, bearer)
  window.location.href = '/'
}

const onFormSubmit = async (values) => {
  if (category.value === '') {
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
      category_id: category.value,
      provider: 'form'
    }
  })
}

const onExternalSubmit = async (provider: Provider) => {
  if (category.value === '') {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'missing_category'
    return
  }

  const data: LoginData = {
    query: {
      category_id: category.value,
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

  // TODO: Remove this when https://github.com/hey-api/openapi-ts/issues/963 is fixed
  const client = createClient(createConfig())
  client.setConfig({
    baseUrl: '/authentication'
  })
  client.interceptors.request.use((request) => {
    request.headers.set('Authorization', 'Bearer ' + bearer)

    return request
  })

  await submitLogin({
    client: client,
    query: {
      category_id: categoryId,
      provider: 'form'
    }
  })
}

const onForgotPassword = () => {
  if (category.value === '') {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'missing_category'
    return
  }

  window.location.href = '/forgot-password?categoryId=' + category.value
}

// Redirect to the maintenance page if there's a maintenance error
watch(error, (newErr) => {
  if (newErr && newErr.message.includes('503')) {
    window.location.href = '/maintenance'
  }
})

// Set the locale if there's a configuration set
watch(config, (newCfg) => {
  if (newCfg?.locale?.default) {
    setLocale(i18n, newCfg.locale.default)
  }
})
</script>

<template>
  <LoginLayout
    :loading="isPending"
    :hide-locale-switch="config?.locale?.hide"
    :hide-logo="config?.logo?.hide"
    :title="config?.info?.title"
  >
    <template v-if="config?.notification" #cover>
      <Alert variant="destructive">
        <Icon
          v-if="config.notification.icon"
          :name="config.notification.icon"
          class="rounded-[1px] outline outline-1 outline-offset-[10px] outline-gray-warm-300"
        />
        <AlertTitle v-if="config.notification.title">{{ config.notification.title }}</AlertTitle>
        <AlertDescription>
          <p v-if="config.notification.description">{{ config.notification.description }}</p>

          <Button
            v-if="config.notification.button"
            hierarchy="link-color"
            class="p-0 mt-4"
            as="a"
            :href="config.notification.button.url"
            >{{ config.notification.button.text }}</Button
          >
        </AlertDescription>
      </Alert>
    </template>

    <template #default>
      <div class="flex flex-col space-y-4">
        <Skeleton v-if="isPending" class="h-6" />

        <Alert v-else-if="isError" variant="destructive">{{ t('authentication.login.errors.unknown') }}</Alert>

        <template v-else>
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
              v-model:modelValue="categoriesDropdownModel"
              :categories="categories"
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
