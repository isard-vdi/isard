<template>
  <component :is="detailComponent"> </component>
</template>

<script lang="ts">
import DefaultDetail from '@/components/details/DefaultDetail.vue';
import { useStore } from '@/store';
import { ComputedRef, shallowRef } from '@vue/reactivity';
import { computed, watch } from '@vue/runtime-core';
import { sections } from '@/config/sections';
import routes from '@/router';

export default {
  name: 'Detail',
  setup() {
    console.log('entra setup detail');
    const store = useStore();
    const detailComponent = shallowRef();

    const section: ComputedRef<any> = computed(() => store.getters.section);

    watch(
      routes.currentRoute,
      async (route) => {
        try {
          const componentName: string = sections[section.value].config?.detail;
          const component = await import(
            `@/components/details/${componentName}.vue`
          );
          detailComponent.value = component?.default || DefaultDetail;
        } catch (e) {
          console.log(e, 'error');
          detailComponent.value = DefaultDetail;
        }
      },
      { immediate: true }
    );
    return {
      detailComponent
    };
  }
};
</script>
