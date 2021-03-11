<template>
  <div :class="containerClass">
    <AppTopBar />

    <transition name="layout-sidebar">
      <div v-show="isMenuVisible" :class="sidebarClass">
        <Language />
        <div class="layout-logo">
          <router-link :to="{ name: 'admin' }">
            <img alt="Logo" width="50" src="@/assets/logo.svg" />
          </router-link>
        </div>
        <p>ISARDVDI</p>

        <AppProfile />
        <AppMenu :menu="menu" />
      </div>
    </transition>

    <div class="layout-main">
      <slot />
    </div>

    <AppFooter />
  </div>
</template>

<script>
import AppTopBar from '@/components/shared/AppTopbar.vue';
import AppProfile from '@/components/shared/AppProfile.vue';
import AppMenu from '@/components/shared/AppMenu.vue';
import AppFooter from '@/components/shared/AppFooter.vue';
import Language from '@/components/Language.vue';
import { menu } from '@/config/menu';

import { useStore } from '@/store';
import { computed } from 'vue';

export default {
  name: 'MainLayout',

  components: {
    AppTopBar,
    AppProfile,
    AppMenu,
    AppFooter,
    Language
  },

  setup() {
    const store = useStore();

    const isMenuVisible = computed(() => store.getters.isMenuVisible);

    const containerClass = computed(() => [
      'layout-wrapper',
      {
        'layout-overlay': store.getters.menuType === 'overlay',
        'layout-static': store.getters.menuType === 'static',
        'layout-static-sidebar-inactive':
          !store.getters.isMenuVisible && store.getters.menuType === 'static',
        'layout-overlay-sidebar-active':
          store.getters.isMenuOverlayActive &&
          store.getters.menuType === 'overlay',
        'layout-mobile-sidebar-active': store.getters.isMenuMobileActive
      }
    ]);

    const sidebarClass = computed(() => [
      'layout-sidebar',
      {
        'layout-sidebar-dark': store.getters.menuColorMode === 'dark',
        'layout-sidebar-light': store.getters.menuColorMode === 'light'
      }
    ]);

    return {
      menu,
      isMenuVisible,
      containerClass,
      sidebarClass
    };
  }
};
</script>

<style scoped lang="scss"></style>
