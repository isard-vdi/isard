<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'

import { Header } from '@/components/header'
import { Sidebar } from '@/components/sidebar'
import { FrontendToggler } from '@/components/frontend-toggler'
import SessionModal from '@/components/modal/SessionModal.vue'
import { MessageModal } from '@/components/modal'

import { useSessionStore } from '@/stores/session'
import { sidebarItemsToShow } from '@/lib/navigation'
import {
  getUserApiV4ItemUserGetOptions,
  getUserConfigApiV4ItemUserGetConfigGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const { t } = useI18n()
const route = useRoute()
const sessionStore = useSessionStore()

const { data: userConfig } = useQuery({
  ...getUserConfigApiV4ItemUserGetConfigGetOptions(),
  staleTime: Infinity
})

const { isPending: isUserLoading, data: user } = useQuery({
  ...getUserApiV4ItemUserGetOptions(),
  staleTime: Infinity
})

// TODO: Uncomment if the TopBar is required
// const navItems = computed(() => getRoleTopBarItems(user.value?.role as Role).mainItems)
const sidebarItems = computed(() => {
  const result = sidebarItemsToShow(
    user?.value.role,
    route.name as string,
    user?.value.items_in_bin,
    userConfig?.value.show_bookings_button ?? true
  ) ?? {
    mainItems: [],
    footerItems: []
  }

  return {
    mainItems: result.mainItems,
    footerItems: result.footerItems.map((item) => {
      if (item.key === 'help') {
        return {
          ...item,
          subItems: item.subItems?.map((subItem) => {
            if (subItem.key === 'docs') {
              return {
                ...subItem,
                href:
                  userConfig?.value?.documentation_url || 'https://isard.gitlab.io/isardvdi-docs/'
              }
            }
            if (subItem.key === 'viewers') {
              return {
                ...subItem,
                href:
                  userConfig?.value?.viewers_documentation_url ||
                  'https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/'
              }
            }
            return subItem
          })
        }
      }
      return item
    })
  }
})

// Initialize session management when component mounts
onMounted(() => {
  sessionStore.initialize()
})

// Cleanup on unmount
onUnmounted(() => {
  sessionStore.$reset()
})
</script>

<template>
  <!-- TODO: Uncomment if the TopBar is required -->
  <!-- <TopBar
    :loading="isUserLoading"
    :user="user"
    :items="navItems"
    :is-connected="isConnected"
    class="bg-[#2d3436] fixed top-0 left-0 right-0 z-50 h-[64px] flex flex-row items-center justify-center"
  />
  <div class="flex flex-row items-center my-6 mx-8">
    <Header :title="t(route.meta.title)" :subtitle="t(route.meta.subtitle)" />
  </div>
  <div class="flex justify-center items-center pb-16 shrink-0">
    <RouterView class="z-10" />
  </div>
  <img src="@/assets/img/mountains.svg" class="fixed bottom-0 right-0 z-0" /> -->
  <Sidebar
    v-if="user"
    :loading="isUserLoading"
    :user="user"
    :items="sidebarItems.mainItems"
    :footer-items="sidebarItems.footerItems"
    @logout="sessionStore.handleLogout"
  >
    <template #header>
      <Header :title="t(route.meta.title)" :subtitle="t(route.meta.subtitle)" />
    </template>
    <template #container>
      <div class="bg-base-background w-full h-full p-8 z-0 relative">
        <RouterView />
        <div
          v-if="route.meta.showDotsBg"
          class="absolute bottom-0 left-0 right-0 top-0 -z-10 select-none flex flex-col justify-center items-center"
        >
          <img src="@/assets/img/bg-dots.svg" class="size-200" />
        </div>
        <img
          v-if="route.meta.showMountainBg"
          src="@/assets/img/mountains.svg"
          class="fixed bottom-0 right-0 -z-10 select-none"
        />
        <img
          v-if="route.meta.showCloudsBg"
          src="@/assets/img/clouds.svg"
          class="absolute top-12 left-20 md:left-40 -z-10 select-none"
        />
      </div>
    </template>
  </Sidebar>

  <SessionModal
    :open="sessionStore.modalOpen"
    :kind="sessionStore.modalKind"
    @renew="sessionStore.renewSession"
    @logout="sessionStore.handleLogout"
    @go-to-login="sessionStore.redirectToLogin"
  />

  <MessageModal />

  <FrontendToggler />
</template>
