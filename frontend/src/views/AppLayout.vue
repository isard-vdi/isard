<template>
  <component :is="layout">
    <Dialog
      v-model:visible="isLoading"
      modal="true"
      show-header="false"
      header="Cancel"
      style="width: 140px; background: rgba(255, 255, 255, 0.5)"
    >
      <br />
      <ProgressSpinner />
      <p></p>
      <br />
      <template #footer>
        <p>Loading ...</p>
      </template>
    </Dialog>
    <slot />
  </component>
</template>

<script lang="ts">
import DefaultLayout from '@/views/DefaultLayout.vue';
import { computed, ComputedRef, ref, shallowRef, watch } from 'vue';
import routes from '@/router';
import Dialog from 'primevue/dialog';
import ProgressSpinner from 'primevue/progressspinner';
import { useStore } from '@/store';

export default {
  name: 'AppLayout',
  components: {
    Dialog: Dialog,
    ProgressSpinner: ProgressSpinner
  },
  setup() {
    const store = useStore();
    const layout = shallowRef();

    const isLoading: ComputedRef<any> = computed(() => store.getters.isLoading);

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
    return { layout, isLoading };
  }
};
</script>
