<template>
  <div>
    <SidebarMenu />
    <div class="p-d-flex p-jc-center">
      <slot />
    </div>
  </div>
</template>

<script>
import SidebarMenu from '@/components/SidebarMenu.vue';

export default {
  name: 'EntityLayout',
  components: {
    SidebarMenu
  }
};
</script>

<style scoped lang="scss"></style>
