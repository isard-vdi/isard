<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/button/Button.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  removeToken as removeAuthToken,
  useCookies as useAuthCookies,
  getToken as getAuthToken
} from '@/lib/auth'

const router = useRouter()
const { t } = useI18n()

interface Props {
  goBack: boolean
  avatar: boolean
  user: {
    name: string
    role: string
    img: string
  }
}

const props = withDefaults(defineProps<Props>(), {
  goBack: false,
  avatar: false,
  user: () => ({
    name: '',
    role: '',
    img: ''
  })
})

const cookies = useAuthCookies()

const goToDesktops = () => {
  window.location.pathname = '/'
}

const logOut = () => {
  if (getAuthToken(cookies)) {
    removeAuthToken(cookies)
  } else {
    router.push({ name: 'login' })
  }
}
</script>
<template>
  <div class="flex h-screen min-h-screen overflow-y-auto bg-base-background">
    <div class="flex justify-between h-full absolute p-8">
      <template v-if="props.goBack">
        <Button
          icon="arrow-left"
          hierarchy="link-color"
          class="text-lg w-min absolute"
          @click="goToDesktops"
        >
          {{ t('layouts.single-page.go-back') }}
        </Button>
      </template>
    </div>

    <div
      v-if="props.avatar"
      class="hidden sm:flex flex-col justify-between items-center w-[80px] h-full p-4 pl-8"
    >
      <img
        :src="'/custom/logo.svg'"
        alt="IsardVDI logo"
        class="self-start max-h-[150px] max-w-min h-[50px] m-"
      />
      <div class="flex flex-col w-full self-end mb-[24px] ml-[20px] items-start">
        <div class="flex items-center gap-4">
          <Avatar size="md">
            <AvatarImage :src="props.user.img" alt="@radix-vue" />
            <AvatarFallback>{{ props.user.name.match(/\b(\w)/g)?.join('') }}</AvatarFallback>
          </Avatar>
          <div class="flex flex-col justify-center">
            <p class="font-semibold text-gray-warm-600">{{ props.user.name }}</p>
            <p>{{ props.user.role }}</p>
          </div>
        </div>
        <Button
          icon="log-out-01"
          hierarchy="link-gray"
          class="opacity-80 mt-3 ml-1"
          @click="logOut"
          >{{ t('layouts.single-page.logout') }}</Button
        >
      </div>
    </div>

    <div
      class="w-full md:w-full h-full min-h-screen p-[32px] flex flex-col justify-between overflow-y-auto"
    >
      <div class="h-full self-center flex flex-col w-full z-20">
        <div class="flex justify-between items-center"></div>
        <slot name="title" />
        <div>
          <slot name="main" />
        </div>
      </div>
    </div>
  </div>
  <img src="@/assets/img/clouds.svg" class="fixed top-[75px] left-[100px] z-10" />
  <img src="@/assets/img/mountains.svg" class="fixed bottom-0 right-0 z-10" />
</template>
