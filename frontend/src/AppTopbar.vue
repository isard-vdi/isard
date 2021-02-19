<template>
  <div class="layout-topbar">
    <button class="p-link layout-menu-button" @click="f_MenuToggle">
      <span class="pi pi-bars"></span>
    </button>
    <div class="layout-topbar-icons">
      <span class="layout-topbar-search">
        <InputText type="text" placeholder="Search" />
        <span class="layout-topbar-search-icon pi pi-search"></span>
      </span>
      <button class="p-link">
        <span class="layout-topbar-item-text">Events</span>
        <span class="layout-topbar-icon pi pi-calendar"></span>
        <span class="layout-topbar-badge">5</span>
      </button>
      <button class="p-link">
        <span class="layout-topbar-item-text">Settings</span>
        <span class="layout-topbar-icon pi pi-cog"></span>
      </button>
      <button class="p-link">
        <span class="layout-topbar-item-text">User</span>
        <span class="layout-topbar-icon pi pi-user"></span>
      </button>
    </div>
  </div>
</template>

<script>
import { useStore } from '@/store';
import { ActionTypes } from '@/store/actions';

export default {
  setup() {
    const store = useStore();

    const f_MenuToggle = () => {
      store.dispatch(ActionTypes.TOGGLE_MENU);
      if (window.innerWidth > 1024) {
        if (store.getters.menuType === 'overlay') {
          if (store.getters.mobileMenuActive === true) {
            store.dispatch(ActionTypes.CHANGE_MENU_OVERLAY_ACTIVE, true);
          }

          store.dispatch(
            ActionTypes.CHANGE_MENU_OVERLAY_ACTIVE,
            !store.getters.menuOverlayActive
          );
          store.dispatch(ActionTypes.CHANGE_MENU_MOBILE_ACTIVE, false);
        } else if (store.getters.menuType === 'static') {
          store.dispatch(
            ActionTypes.CHANGE_MENU_STATIC_INACTIVE,
            !store.getters.staticMenuInactive
          );
        }
      } else {
        store.dispatch(
          ActionTypes.CHANGE_MENU_MOBILE_ACTIVE,
          !store.getters.mobileMenuActive
        );
      }
    };

    return {
      f_MenuToggle
    };
  }
};
</script>
