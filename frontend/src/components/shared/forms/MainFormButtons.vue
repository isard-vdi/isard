<template>
  <div class="p-grid p-jc-end p-m-2">
    <!-- buttons -->
    <isard-button v-if="editMode" label="Cancel" @click="endEditMode" />
    <isard-button
      v-if="editMode"
      label="Save"
      :disabled="!formChanged"
      @click="formChanged && $emit('savebutton-pressed')"
    />
    <isard-button
      v-if="!editMode"
      label="Edit"
      :disabled="!editEnabled"
      @click="goToEditMode"
    />
  </div>
</template>

<script lang="ts">
import IsardButton from './IsardButton.vue';
import { ActionTypes } from '@/store/actions';
import { computed } from '@vue/runtime-core';
import { useStore } from '@/store';

export default {
  components: { IsardButton },
  props: {
    editEnabled: Boolean,
    formChanged: Boolean,
    hola: Boolean
  },
  emits: ['savebutton-pressed'],
  setup(
    props: Readonly<
      {
        editEnabled: boolean;
        formChanged: boolean;
      } & {}
    >
  ) {
    const store = useStore();
    const editMode = computed(() => store.getters.editMode);

    function goToEditMode() {
      props.editEnabled && store.dispatch(ActionTypes.ACTIVATE_EDIT_MODE, {});
    }

    function endEditMode() {
      store.dispatch(ActionTypes.END_EDIT_MODE, {});
    }

    return {
      editMode,
      endEditMode,
      goToEditMode
    };
  }
};
</script>
