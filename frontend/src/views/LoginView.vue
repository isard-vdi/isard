<script setup lang="ts">
import { LoginLayout } from '@/layouts/login'
import { LoginProviderForm, LoginProviderExternal, Provider } from '@/components/login'
import { Separator } from '@/components/ui/separator'
</script>

<template>
  <LoginLayout version="v13.3.2">
    <div class="flex flex-col space-y-4">
      <LoginProviderForm />

      <Separator />

      <LoginProviderExternal :provider="Provider.Google" />
      <LoginProviderExternal :provider="Provider.SAML" />
    </div>
  </LoginLayout>
</template>
