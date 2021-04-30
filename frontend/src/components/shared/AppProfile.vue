<template>
  <div class="layout-profile">
    <div>
      <img src="@/assets/logo.png" alt="" />
    </div>
    <button class="p-link layout-profile-link">
      <span class="username">{{ user.name }} {{ user.surname }}</span>
    </button>
  </div>
</template>

<script>
import { useStore } from '@/store';
import { defineComponent, computed } from 'vue';

export default defineComponent({
  setup() {
    const store = useStore();
    const user = computed(() => store.getters.userData);
    return { user };
  }
});
</script>

<style scoped></style>
