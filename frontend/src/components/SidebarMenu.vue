<template>
  <Button
    icon="pi pi-arrow-left"
    class="p-mr-2"
    @click="visibleLeft = !visibleLeft"
  />
  <Sidebar
    :visible="visibleLeft"
    :auto-z-index="true"
    :show-close-icon="false"
    :modal="false"
  >
    <img id="logo" alt="IsardVDI" src="@/assets/logo.svg" />
    <h3>IsardVDI</h3>

    <PanelMenu :model="items" />
  </Sidebar>
</template>

<script lang="ts">
import { computed, defineComponent } from 'vue';
import { menu } from '@/config/menu';

export default defineComponent({
  name: 'SidebarMenu',
  components: {},
  data() {
    return {
      visibleLeft: true,
      items: menu
    };
  }
});
</script>

<style scoped lang="scss">
#logo {
  margin-top: 20px;
  max-width: 50px;
}
</style>
