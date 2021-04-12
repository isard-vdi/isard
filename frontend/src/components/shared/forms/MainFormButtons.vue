<template>
  <div class="p-grid p-jc-end p-m-2">
    <isard-button
      v-if="editMode"
      label="Cancel"
      data-testid="buttCancel"
      @click.stop="endEditMode"
    />
    <isard-button
      v-if="editMode"
      label="Save"
      :disabled="!formChanged"
      data-testid="buttSave"
      @click.stop="formChanged && $emit('savebutton-pressed')"
    />
    <isard-button
      v-if="!editMode && !createMode"
      label="Edit"
      :disabled="!editEnabled"
      data-testid="buttEdit"
      @click.stop="goToEditMode"
    />
    <isard-button
      v-if="createMode"
      label="Save New"
      class="buttSaveNew"
      @click.stop="$emit('savenewbutton-pressed')"
    />
  </div>
</template>

<script lang="ts">
import IsardButton from '@/components/shared/forms/IsardButton.vue';
import { ActionTypes } from '@/store/actions';
import { computed } from '@vue/runtime-core';
import { useStore } from '@/store';

export default {
  components: { IsardButton },
  props: {
    editEnabled: {
      type: Boolean,
      required: true
    },
    formChanged: {
      type: Boolean,
      required: true
    },
    createMode: {
      type: Boolean,
      required: true
    }
  },
  emits: ['savebutton-pressed', 'savenewbutton-pressed'],
  setup(
    props: Readonly<
      {
        editEnabled: boolean;
        formChanged: boolean;
        createMode: boolean;
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
      goToEditMode,
      endEditMode
    };
  }
};
</script>
