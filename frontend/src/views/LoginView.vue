<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { jwtDecode } from 'jwt-decode'
import { set as setCookie } from 'tiny-cookie'
import { useQuery } from '@tanstack/vue-query'
import { login, LoginData } from '@/gen/oas/authentication'
import { getCategoriesOptions } from '@/gen/oas/api/@tanstack/vue-query.gen'
import { LoginLayout } from '@/layouts/login'
import {
  LoginProviderForm,
  LoginProviderExternal,
  LoginCategoriesDropdown,
  Provider
} from '@/components/login'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()
const route = useRoute()

// TODO: Router push to /login
const isProviderValid = computed(() => {
  const provider = route.params.provider as Provider
  return provider && Object.values(Provider).includes(provider)
})

const {
  isPending: categoriesIsPending,
  isError: categoriesIsError,
  data: categories
} = useQuery(getCategoriesOptions())

// TODO: Move this to the API call
const showCategoryDropdown = true
const categoryDropdownModel = ref('')

const category = computed(() => {
  if (route.params.category !== '') {
    // TODO: Filter from categories URL
    return route.params.category
  }

  if (showCategoryDropdown) {
    return categoryDropdownModel.value
  }

  // Fallback to the 'default' category if there's no category
  // in the URL and the dropdown isn't shown. This is useful for
  // external providers that can guess the category
  return 'default'
})

const categoryDropdownEl = ref<InstanceType<typeof LoginCategoriesDropdown> | null>(null)
const focusCategorySelect = () => {
  categoryDropdownEl.value?.focus()
}

const onFormSubmit = async (values) => {
  if (category.value === '') {
    if (showCategoryDropdown) {
      focusCategorySelect()
      return
    }

    throw 'AAAAAAAAAAAAAAAAA'
  }

  const { error, response } = await login({
    body: values,
    query: {
      category_id: category.value,
      provider: 'form'
    }
  })

  if (error !== undefined) {
    // TODO: Handle error! :D
    console.error('ERROR FROM CLIENT!!!!')
    console.error(error)
  } else {
    const authorization = response.headers.get('authorization')
    if (authorization === null) {
      // TODO: Handle error here
      throw 'AAAAAAAAAAA :('
    }

    const bearer = authorization.replace(/^Bearer /g, '')
    if (bearer.length === authorization.length) {
      // TODO: No bearer :( , handle error
      throw 'AAAAAAAAAAA :('
    }

    // TODO: Try except???
    // TODO: Remove this library
    const jwt = jwtDecode(bearer)
    switch (jwt.type) {
      case 'category-select':
        // TODO: Choose your fighter
        break

      default:
        // TODO :Set cookie and redirect
        // TODO: Remove this library
        // TODO: Move this to a constant
        // TODO: Eval to simply use the authentication already set cookie
        setCookie('isardvdi_session', bearer)
        window.location = '/'
        break
    }
  }
}

const onExternalSubmit = async (provider: Provider) => {
  if (category.value === '') {
    if (showCategoryDropdown) {
      focusCategorySelect()
      return
    }

    throw 'AAAAAAAAAAAAAAAAA'
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
</script>

<template>
  <LoginLayout>
    <div class="flex flex-col space-y-4">
      <LoginCategoriesDropdown
        v-if="
          route.params.category === '' &&
          showCategoryDropdown &&
          !categoriesIsPending &&
          !categoriesIsError
        "
        ref="categoryDropdownEl"
        v-model:modelValue="categoryDropdownModel"
        :categories="categories"
      />

      <LoginProviderForm v-if="!isProviderValid" @submit="onFormSubmit" />

      <Separator v-if="!isProviderValid" :label="t('views.login.separator')" />

      <template v-for="provider in Object.values(Provider)" :key="provider">
        <LoginProviderExternal
          v-if="!isProviderValid || route.params.provider === provider"
          :provider="provider"
          @submit="onExternalSubmit"
        />
      </template>
    </div>
  </LoginLayout>
</template>
