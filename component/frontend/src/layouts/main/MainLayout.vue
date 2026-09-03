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
import ScrollToTop from '@/components/page/ScrollToTop.vue'

import { useSessionStore } from '@/stores/session'
import { sidebarItemsToShow } from '@/lib/navigation'
import { DEFAULT_DOCS_URL, DEFAULT_VIEWERS_DOCS_URL, docsUrl } from '@/lib/docs'
import { getUserOptions, getUserConfigOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { cn } from '@/lib/utils'

const { t, locale } = useI18n()
const route = useRoute()
const sessionStore = useSessionStore()

const { data: userConfig } = useQuery({
  ...getUserConfigOptions(),
  staleTime: Infinity
})

const { isPending: isUserLoading, data: user } = useQuery({
  ...getUserOptions(),
  staleTime: Infinity
})

// The desktops grid runs wide by design, so it keeps the spacing the rest of the app grew out of.
const contentPadding = computed(() =>
  route.meta.narrowGutter
    ? '[--page-gutter:1.25rem] p-5'
    : '[--page-gutter:1.5rem] px-[var(--page-gutter)] pb-24 pt-8 md:[--page-gutter:3rem] lg:[--page-gutter:5rem]'
)

// In `hidden` mode the login notifications page is a transitional landing that
// must funnel the user back to the old frontend.
const redirectToOldFrontend = computed(
  () => route.name === 'notifications' && userConfig?.value?.frontend_mode === 'hidden'
)

// TODO: Uncomment if the TopBar is required
// const navItems = computed(() => getRoleTopBarItems(user.value?.role as Role).mainItems)
const sidebarItems = computed(() => {
  const result = sidebarItemsToShow(
    user?.value.role,
    route.name as string,
    user?.value.items_in_bin,
    userConfig?.value.show_bookings_button ?? true,
    userConfig?.value.show_gpu_plannings ?? false,
    redirectToOldFrontend.value
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
                href: docsUrl(userConfig?.value?.documentation_url, DEFAULT_DOCS_URL, locale.value)
              }
            }
            if (subItem.key === 'viewers') {
              return {
                ...subItem,
                href: docsUrl(
                  userConfig?.value?.viewers_documentation_url,
                  DEFAULT_VIEWERS_DOCS_URL,
                  locale.value
                )
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
      <!-- The side gutters widen with the viewport so the content does not run edge to edge,
           and the bottom one is deeper still so the floating buttons never land on the last
           row of a page. Full-bleed children read the gutter back off --page-gutter. -->
      <div
        :class="cn('bg-base-background relative z-0 flex w-full flex-1 flex-col', contentPadding)"
      >
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
          class="fixed bottom-0 right-0 -z-10 hidden select-none md:block"
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

  <!-- Both float in the same corner, so they stack instead of overlapping when both are up. -->
  <div class="pointer-events-none fixed bottom-6 right-6 z-40 flex flex-col items-end gap-3">
    <ScrollToTop />
    <FrontendToggler />
  </div>
</template>
