<script setup lang="ts">
import { LoginLayout } from '@/layouts/login'
import { LoginProviderForm, LoginProviderExternal, Provider } from '@/components/login'
import { Separator } from '@/components/ui/separator'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const { t } = useI18n()
const route = useRoute()

const isProviderValid = computed(() => {
  const provider = route.params.provider as Provider
  return provider && Object.values(Provider).includes(provider)
})
</script>

<template>
  <LoginLayout version="v13.3.2">
    <div class="flex flex-col space-y-4">
      <LoginProviderForm />

      <Separator v-if="!isProviderValid" :label="t('views.login.separator')" />

      <LoginProviderExternal :provider="Provider.Google" />
      <LoginProviderExternal :provider="Provider.SAML" />
    </div>
  </LoginLayout>
</template>
