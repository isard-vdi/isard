<template>
  <div class="about">
    <h1>{{ counter }}</h1>
    <button @click="addOne">Add 1</button>
  </div>
</template>

<script lang="ts">
import { computed } from 'vue';
import { useStore } from 'vuex';

export default {
  name: 'About',
  setup() {
    const store = useStore();

    return {};
  }
};
</script>
