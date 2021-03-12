<template>
  <div class="layout-menu-container">
    <AppSubmenu :items="menu" class="layout-menu" :root="true" />
  </div>
</template>

<script>
import AppSubmenu from './AppSubmenu';

export default {
  components: {
    AppSubmenu: AppSubmenu
  },
  props: {
    menu: {
      required: true,
      type: Array
    }
  }
};
</script>

<style scoped></style>
