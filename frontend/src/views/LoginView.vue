<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { jwtDecode } from 'jwt-decode'
import { set as setCookie } from 'tiny-cookie'
import { login } from '@/gen/oas/authentication'
import { LoginLayout } from '@/layouts/login'
import { LoginProviderForm, LoginProviderExternal, Provider } from '@/components/login'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()
const route = useRoute()

const isProviderValid = computed(() => {
  const provider = route.params.provider as Provider
  return provider && Object.values(Provider).includes(provider)
})

const onFormSubmit = async (values) => {
  const { data, error, response } = await login({
    body: values,
    query: {
      // TODO: Softcode this
      category_id: 'default',
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
</script>

<template>
  <LoginLayout version="v13.3.2">
    <div class="flex flex-col space-y-4">
      <LoginProviderForm v-if="!isProviderValid" @submit="onFormSubmit" />

      <Separator v-if="!isProviderValid" :label="t('views.login.separator')" />

      <template v-for="provider in Object.values(Provider)" :key="provider">
        <LoginProviderExternal
          v-if="!isProviderValid || $route.params.provider === provider"
          :provider="provider"
        />
      </template>
    </div>
  </LoginLayout>
</template>
