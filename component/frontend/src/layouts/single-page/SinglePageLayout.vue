<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/button/Button.vue'
import { AvatarLabel } from '@/components/avatar-label'
import {
  removeToken as removeAuthToken,
  useCookies as useAuthCookies,
  getToken as getAuthToken
} from '@/lib/auth'

const router = useRouter()
const { t } = useI18n()

interface Props {
  goBack?: boolean
  avatar?: boolean
  user?: {
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
    <div class="flex justify-between h-full absolute p-8 z-30">
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
        :src="'/api/v4/logo'"
        alt="IsardVDI logo"
        class="self-start max-h-[150px] max-w-min h-[50px] m-"
      />
      <div class="flex flex-col w-full self-end mb-[24px] ml-[20px] items-start">
        <div class="flex items-center gap-4">
          <AvatarLabel
            size="md"
            :src="props.user.img"
            :name="props.user.name"
            :sub="props.user.role"
          />
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
  <img
    src="@/assets/img/clouds.svg"
    class="fixed top-[75px] left-[100px] z-10 pointer-events-none invisible xl:visible"
  />
  <img src="@/assets/img/mountains.svg" class="fixed bottom-0 right-0 z-10 pointer-events-none" />
</template>
