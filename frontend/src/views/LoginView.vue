<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoginLayout } from '@/layouts/login'
import { LoginProviderForm, LoginProviderExternal, Provider } from '@/components/login'
import { Separator } from '@/components/ui/separator'

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
      <LoginProviderForm v-if="!isProviderValid" />

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
