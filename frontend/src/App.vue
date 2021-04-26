<template>
  <div id="app">
    <AppLayout>
      <router-view />
    </AppLayout>
  </div>
</template>

<script>
import AppLayout from '@/views/AppLayout.vue';
export default {
  components: {
    AppLayout: AppLayout
  }
};
</script>
