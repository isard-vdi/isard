<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { isardVdiUrl } from '@/lib/constants'
import { LocaleSwitch } from '@/components/locale-switch'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getToken as getAuthToken,
  removeToken as removeAuthToken,
  useCookies as useAuthCookies
} from '@/lib/auth'

const router = useRouter()
const { t } = useI18n()
const cookies = useAuthCookies()

interface Props {
  loading?: boolean
  hideLocaleSwitch?: boolean
  hideLogo?: boolean
  title?: string
  description?: string
  loginButtonText?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  hideLocaleSwitch: false,
  hideLogo: false,
  title: undefined,
  description: undefined,
  loginButtonText: undefined
})

const cleanCookiesAndGoToLogin = () => {
  if (getAuthToken(cookies)) {
    removeAuthToken(cookies)
  } else {
    router.push({ name: 'login' })
  }
}
</script>

<template>
  <div class="flex h-screen overflow-y-auto overflow-x-hidden bg-base-background">
    <!-- Left panel (content) -->
    <div
      class="w-full md:w-1/2 md:mr-[50%] h-full p-[32px] px-[64px] flex flex-col justify-between z-10 gap-[32px<]"
    >
      <!-- Language selector -->
      <div class="self-start">
        <LocaleSwitch v-if="!loading && !props.hideLocaleSwitch" />
      </div>

      <!-- Content -->
      <div class="self-center items-start flex flex-col relative w-full">
        <div
          class="bg-dots-img w-[480px] h-[480px] absolute top-[calc(-100px)] left-[-60px] z-[-1]"
        />

        <img
          v-if="!loading && !props.hideLogo"
          class="self-start max-h-[150px]"
          :src="'/custom/logo.svg'"
          alt="IsardVDI logo"
        />
        <Skeleton v-if="loading" class="h-6 w-1/3 mt-[46px] mb-[32px]" />
        <h1
          v-if="!loading"
          class="mt-[46px] mb-[32px] text-left text-display-lg font-bold text-gray-warm-900 hyphens-auto"
        >
          {{ props.title || t('layouts.maintenance.title') }}
        </h1>

        <Skeleton v-if="loading" class="h-6 w-full mb-2" />
        <Skeleton v-if="loading" class="h-6 w-full mb-[32px]" />
        <h2 v-if="!loading" class="text-left text-md mb-[32px] text-gray-warm-600">
          {{ props.description || t('layouts.maintenance.description') }}
        </h2>

        <Button @click="cleanCookiesAndGoToLogin()">
          {{ props.loginButtonText || t('layouts.maintenance.button') }}
        </Button>
      </div>

      <!-- Extra info -->
      <div class="self-center flex">
        <div>
          <p>
            {{ t('layouts.login.works-with') }}
            <a class="font-bold hover:underline" :href="isardVdiUrl">IsardVDI</a>
          </p>
        </div>
      </div>
    </div>

    <!-- Right panel (cover image) -->
    <div
      class="hidden md:block md:ml-[50%] w-1/2 h-full bg-cover bg-center bg-maintenance-img px-20 content-center fixed"
    >
      <slot name="cover" />
    </div>
  </div>
</template>
