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
import IsardButton from '@/components/shared/forms/IsardButton.vue';

export default {
  components: {
    IsardButton: IsardButton
  },
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
