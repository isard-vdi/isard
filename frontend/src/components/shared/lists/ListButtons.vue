<template>
  <div class="p-grid p-jc-end p-m-2">
    <isard-button
      label="Create New"
      :disabled="!createEnabled"
      @click="createEnabled && $emit('createbutton-pressed')"
    />
  </div>
</template>

<script lang="ts">
import { useStore } from '@/store';

export default {
  props: {
    createEnabled: Boolean
  },
  emits: ['createbutton-pressed'],
  setup(
    props: Readonly<
      {
        createEnabled: boolean;
      } & {}
    >
  ) {
    const store = useStore();

    return {};
  }
};
</script>
