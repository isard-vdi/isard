<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import error403 from '@/assets/img/error/error-403.svg'
import error400 from '@/assets/img/error/error-400.svg'
import error404 from '@/assets/img/error/error-404.svg'
import error500 from '@/assets/img/error/error-500.svg'
import icon403 from '@/assets/img/error/icon-error-403.svg'
import icon500 from '@/assets/img/error/icon-error-500.svg'
import icon400 from '@/assets/img/error/icon-error-400.svg'
import icon404 from '@/assets/img/error/icon-error-404.svg'
import greenMountain from '@/assets/img/error/green-mountain.svg'
import blueMountain from '@/assets/img/error/blue-mountain.svg'
import cloud from '@/assets/img/error/cloud.svg'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useSessionStore } from '@/stores/session'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const authStore = useAuthStore()

const errorTypes = {
  '400': { img: error400, icon: icon400 },
  '403': { img: error403, icon: icon403 },
  '404': { img: error404, icon: icon404 },
  '500': { img: error500, icon: icon500 }
}

const error = computed(() => {
  const code = errorTypes[route.params.code as keyof typeof errorTypes]
    ? (route.params.code as string)
    : '500'
  return { code, ...errorTypes[code] }
})

onMounted(() => {
  sessionStore.initialize()
})

onUnmounted(() => {
  sessionStore.$reset()
})

const handleGoBack = () => {
  if (!authStore.isAuthenticated) return router.push({ name: 'login' })
  if (error.value.code === '404') return router.push({ name: 'desktops' })
  router.go(-1)
}

const handleGoToLogin = () =>
  authStore.isAuthenticated ? sessionStore.handleLogout() : router.push({ name: 'login' })
</script>

<template>
  <div
    class="bg-base-white tall:grid tall:place-items-center md:bg-base-background w-full h-screen overflow-hidden"
  >
    <section
      class="py-10 px-10 min-h-250 overflow-hidden sm:py-20 sm:px-12 md:py-35 md:h-screen tall:h-fit tall:min-w-max tall:pt-55 md:pb-[530px] md:px-80 img-xl:px-120 bg-base-white w-fit img-xl:w-full img-xl:max-w-480 h-auto m-auto relative md:shadow-2xl z-10 flex justify-center"
    >
      <div class="max-w-120 img-xl:max-w-480 flex flex-col gap-3">
        <div>
          <h1
            class="relative text-[80px] sm:text-[130px] md:text-[180px] lg:text-[230px] font-bold text-left text-brand-700 mb-6 sm:mb-12 md:mb-25"
          >
            {{ error.code }}
            <img
              :src="cloud"
              alt="cloud"
              class="mt-20 w-25 hidden sm:block sm:mt-0 absolute left-0 -top-45 md:-left-60 md:-top-15 sm:w-45 animate-float"
            />
          </h1>
          <div class="flex gap-5 items-center justify-left">
            <h2 class="text-lg sm:text-xl md:text-2xl lg:text-[30px] font-bold text-left">
              {{ t(`views.error.${error.code}.title`) }}
            </h2>
            <img class="w-10 h-10 md:w-15 md:h-15" :src="error.icon" alt="" />
          </div>
        </div>
        <p class="text-sm sm:text-base md:text-lg text-left">
          {{ t(`views.error.${error.code}.description`) }}
        </p>
        <Separator />
        <div class="flex flex-col justify-between sm:flex-row">
          <Button icon="arrow-left" hierarchy="link-color" @click="handleGoBack">
            {{ t('views.error.actions.go_back') }}
          </Button>
          <Button icon="log-out-01" hierarchy="link-color" @click="handleGoToLogin">
            {{ t('views.error.actions.go_to_login') }}
          </Button>
        </div>
        <Separator class="hidden sm:flex" />
      </div>
      <div
        class="fixed md:absolute bottom-0 left-1/2 -translate-x-1/2 w-[150%] max-w-hero-img pointer-events-none"
      >
        <img :src="error.img" alt="illustration error" class="w-full select-none" />
      </div>
    </section>
    <img
      :src="blueMountain"
      alt="mountain"
      class="fixed right-0 bottom-0 w-[80%] opacity-0 md:opacity-50"
    />
    <img
      :src="greenMountain"
      alt="mountain"
      class="fixed -left-95 bottom-0 w-[80%] opacity-0 md:opacity-50 tall:opacity-0"
    />
  </div>
</template>
