<template>
  <component :is="layout">
    <slot />
  </component>
</template>

<script lang="ts">
import DefaultLayout from '@/views/DefaultLayout.vue';
import { shallowRef, watch } from 'vue';
import routes from '@/router';
export default {
  name: 'AppLayout',
  setup() {
    const layout = shallowRef();
    watch(
      routes.currentRoute,
      async (route) => {
        try {
          const component = await import(`@/views/${route.meta.layout}.vue`);
          layout.value = component?.default || DefaultLayout;
        } catch (e) {
          layout.value = DefaultLayout;
        }
      },
      { immediate: true }
    );
    return { layout };
  }
};
</script>
