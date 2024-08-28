<script setup lang="ts">
import { computed, type ComputedRef, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { jwtDecode } from 'jwt-decode'
import { set as setCookie, get as getCookie } from 'tiny-cookie'
import { createClient, createConfig, type Options as ClientOptions } from '@hey-api/client-fetch'
import { useQuery } from '@tanstack/vue-query'
import { providersOptions } from '@/gen/oas/authentication/@tanstack/vue-query.gen'
import { login, type LoginData, type error as LoginErrorUnion } from '@/gen/oas/authentication'
import { getCategoriesOptions, getLoginConfigOptions } from '@/gen/oas/api/@tanstack/vue-query.gen'
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
  type CategorySelectToken
} from '@/components/login'
import { Separator } from '@/components/ui/separator'
import { Icon } from '@/components/icon'

const { t, te } = useI18n()
const route = useRoute()

const {
  isPending: providersIsPending,
  isError: providersIsError,
  data: providers
} = useQuery(providersOptions())

const {
  isPending: categoriesIsPending,
  isError: categoriesIsError,
  data: categories
} = useQuery(getCategoriesOptions())

const {
  isPending: configIsPending,
  isError: configIsError,
  data: config
} = useQuery(getLoginConfigOptions())

const isPending = computed(
  () => providersIsPending.value || categoriesIsPending.value || configIsPending.value
)

// TODO: Router push to /login if the provider in the URL is invalid / not active / whatever
const routeProvider = computed(() => {
  if (route.params.provider === 'all') {
    return 'all'
  }

  const routeProvider = route.params.provider as Provider
  const routeProviderValid = Object.values(Provider).includes(routeProvider)

  return routeProviderValid ? routeProvider : null
})

// TODO: Router push to /login/provider if the category invalid / not active / whatever
const routeCategory = computed(() => (route.params.category !== '' ? route.params.category : null))

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

const showCategoriesDropdown = computed(() => {
  const providersConfig = config.value?.providers
  if (providersConfig) {
    let display = true

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
    }

    return display
  }

  // If there's a category set in the URL, don't show the dropdown
  if (routeCategory.value) {
    return false
  }

  return true
})

const categoriesDropdownModel = ref('')
const category = computed(() => {
  if (routeCategory.value) {
    // TODO: Filter from categories URL
    return routeCategory.value
  }

  if (categoriesDropdownModel.value !== '') {
    return categoriesDropdownModel.value
  }

  // Fallback to the 'default' category if there's no category
  // in the URL and the dropdown isn't shown. This is useful for
  // external providers that can guess the category
  return 'default'
})

const categoriesDropdownEl = typeof ref<InstanceType<typeof LoginCategoriesDropdown> | null>(null)
const focusCategoriesDropdown = () => {
  categoriesDropdownEl.value?.focus()
}

const loginError = ref<LoginErrorUnion | 'unknown' | null>(
  route.query.error === undefined ? null : route.query.error
)
const loginErrorMsg = computed(() => {
  const baseKey = 'authentication.login.errors.'
  const key = baseKey + loginError.value
  // Check if the error exists in the base locale
  if (te(key, 'en-US')) {
    return t(key)
  }

  return t(baseKey + 'unknown')
})

const categorySelectToken: typeof ref<CategorySelectToken | null> = (() => {
  // TODO: COnst this
  const savedBearer = getCookie('authorization') || getCookie('isardvdi_session')

  if (savedBearer !== null) {
    const jwt = jwtDecode(savedBearer)
    // TODO: COnst this
    if (jwt.type === 'category-select') {
      return jwt.categories
    }
  }

  return null
})()

const submitLogin = async (options: ClientOptions<LoginData>) => {
  const { error, response } = await login(options)
  if (error !== undefined) {
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

  // TODO: Try except???
  // TODO: Remove this library
  const jwt = jwtDecode(bearer)
  switch (jwt.type) {
    case 'category-select':
      // TODO: Check types?
      categorySelectToken.value = jwt.categories
      break

    default:
      // Login to Webapp
      if ([undefined, '', 'login'].includes(jwt.type)) {
        if (['admin', 'manager'].includes(jwt.data.role_id)) {
          await fetch('/isard-admin/login', {
            method: 'POST',
            headers: {
              Authorization: authorization
            }
          })
        }
      }

      // TODO: Remove this library
      // TODO: Move this to a constant
      // TODO: Eval to simply use the authentication already set cookie

      setCookie('isardvdi_session', bearer)
      window.location.href = '/'
      break
  }
}

const onFormSubmit = async (values) => {
  if (category.value === '') {
    if (showCategoriesDropdown.value) {
      focusCategoriesDropdown()
      return
    }

    loginError.value = 'unknown'
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

    loginError.value = 'unknown'
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
  // TODO: Remove this when https://github.com/hey-api/openapi-ts/issues/963 is fixed
  const client = createClient(createConfig())
  client.setConfig({
    baseUrl: '/authentication'
  })
  client.interceptors.request.use((request) => {
    // TODO: COnst this and move it to a proper function or something
    request.headers.set(
      'Authorization',
      'Bearer ' + (getCookie('authorization') || getCookie('isardvdi_session'))
    )

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
        <Skeleton v-if="providersIsPending || categoriesIsPending || configIsPending" class="h-6" />

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
            />

            <Separator
              v-if="
                !routeProvider &&
                providers?.providers.includes('form') &&
                providers.providers.length > 1
              "
              :label="t('views.login.separator')"
            />

            <template v-for="provider in Object.values(Provider)" :key="provider">
              <LoginProviderExternal
                v-if="provider !== Provider.Form && showProvider(provider).value"
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
